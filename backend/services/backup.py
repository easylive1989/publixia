"""SQLite → Cloudflare R2 daily backup.

Hot-backup the live SQLite DB via `sqlite3.Connection.backup()` (safe
under concurrent writes — file copy would corrupt mid-page), gzip it,
and upload to R2 under `db/stock_dashboard-YYYY-MM-DD.db.gz`.

Retention: keep all daily backups for 30 days; beyond that, keep only
the 1st-of-month snapshots, and only for 1 year.

Skips silently when R2 settings are missing (local dev without
R2_* env vars).
"""
from __future__ import annotations

import gzip
import logging
import os
import sqlite3
import tempfile
from datetime import date, datetime, timedelta, timezone

import pytz

from core.settings import settings

logger = logging.getLogger(__name__)

TST = pytz.timezone("Asia/Taipei")
KEY_PREFIX = "db/"
KEY_TEMPLATE = "db/stock_dashboard-{date}.db.gz"
DAILY_RETENTION_DAYS = 30
MONTHLY_RETENTION_DAYS = 365


def _r2_client():
    """Return a configured boto3 S3 client for R2, or None if unconfigured."""
    if not (settings.r2_access_key_id and settings.r2_secret_access_key
            and settings.r2_endpoint_url and settings.r2_bucket):
        return None
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.r2_secret_access_key.get_secret_value(),
        # R2 only supports `auto`; signature_version v4 is required.
        config=Config(signature_version="s3v4", region_name="auto"),
    )


def _hot_backup(src_path: str, dest_path: str) -> None:
    """sqlite3 online backup — safe while writers hold the live DB."""
    src = sqlite3.connect(src_path)
    try:
        dest = sqlite3.connect(dest_path)
        try:
            src.backup(dest)
        finally:
            dest.close()
    finally:
        src.close()


def _gzip_file(src_path: str, dest_path: str) -> None:
    with open(src_path, "rb") as fin, gzip.open(dest_path, "wb", compresslevel=6) as fout:
        # 1 MiB chunks — keeps RAM bounded for large DBs.
        while True:
            chunk = fin.read(1024 * 1024)
            if not chunk:
                break
            fout.write(chunk)


def _today_tst() -> date:
    return datetime.now(timezone.utc).astimezone(TST).date()


def _should_keep(key: str, today: date) -> bool:
    """Apply retention policy: 30d daily + 1y monthly."""
    name = key[len(KEY_PREFIX):] if key.startswith(KEY_PREFIX) else key
    # Expected: stock_dashboard-YYYY-MM-DD.db.gz
    try:
        stem = name.removeprefix("stock_dashboard-").removesuffix(".db.gz")
        d = datetime.strptime(stem, "%Y-%m-%d").date()
    except ValueError:
        # Unknown layout — keep it; let a human investigate.
        logger.warning("backup_unexpected_key key=%s", key)
        return True
    age = (today - d).days
    if age <= DAILY_RETENTION_DAYS:
        return True
    if d.day == 1 and age <= MONTHLY_RETENTION_DAYS:
        return True
    return False


def _prune(client, bucket: str, today: date) -> int:
    """Delete backups that fall outside the retention policy. Returns count deleted."""
    paginator = client.get_paginator("list_objects_v2")
    to_delete: list[dict] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=KEY_PREFIX):
        for obj in page.get("Contents", []) or []:
            key = obj["Key"]
            if not _should_keep(key, today):
                to_delete.append({"Key": key})
    if not to_delete:
        return 0
    # delete_objects accepts at most 1000 keys per call.
    deleted = 0
    for i in range(0, len(to_delete), 1000):
        batch = to_delete[i:i + 1000]
        resp = client.delete_objects(Bucket=bucket, Delete={"Objects": batch})
        deleted += len(resp.get("Deleted", []) or [])
    return deleted


def backup_db_to_r2() -> bool:
    """Scheduler entrypoint. Returns True on success (or skip), False on error."""
    client = _r2_client()
    if client is None:
        logger.warning("backup_skipped reason=r2_not_configured")
        return True

    today = _today_tst()
    key = KEY_TEMPLATE.format(date=today.isoformat())

    with tempfile.TemporaryDirectory(prefix="dbbackup-") as tmp:
        snap_path = os.path.join(tmp, "snap.db")
        gz_path = os.path.join(tmp, "snap.db.gz")
        try:
            _hot_backup(settings.db_path, snap_path)
            _gzip_file(snap_path, gz_path)
            size = os.path.getsize(gz_path)
            client.upload_file(gz_path, settings.r2_bucket, key)
        except Exception as e:
            logger.exception("backup_upload_failed key=%s err=%s", key, e)
            return False

    logger.info("backup_uploaded key=%s bytes=%d", key, size)

    try:
        n = _prune(client, settings.r2_bucket, today)
        if n:
            logger.info("backup_pruned count=%d", n)
    except Exception as e:
        # Pruning failure shouldn't fail the backup itself.
        logger.exception("backup_prune_failed err=%s", e)

    return True
