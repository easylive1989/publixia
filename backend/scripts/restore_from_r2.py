"""Restore a SQLite backup snapshot from Cloudflare R2.

Downloads `db/stock_dashboard-<DATE>.db.gz` from the configured R2 bucket,
decompresses it, and writes the result to a local path.

By design, the default output path is **not** the live DB — it writes to
`stock_dashboard.restored.db` next to the live one. Swapping it in is a
manual step (stop the service, mv files, restart) so this script can never
silently overwrite live data.

Usage:
    python -m scripts.restore_from_r2 2026-05-09
    python -m scripts.restore_from_r2 2026-05-09 --out /tmp/check.db
    python -m scripts.restore_from_r2 --list
"""
from __future__ import annotations

import argparse
import gzip
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.settings import settings
from services.backup import KEY_PREFIX, KEY_TEMPLATE, _r2_client


def _list_backups(client, bucket: str) -> list[str]:
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=KEY_PREFIX):
        for obj in page.get("Contents", []) or []:
            keys.append(obj["Key"])
    return sorted(keys)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date", nargs="?", help="Backup date (YYYY-MM-DD)")
    parser.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(__file__), "..", "..",
                             "stock_dashboard.restored.db"),
        help="Output path (default: ./stock_dashboard.restored.db)",
    )
    parser.add_argument("--list", action="store_true",
                        help="List available backup keys in the bucket")
    args = parser.parse_args()

    client = _r2_client()
    if client is None:
        print("ERROR: R2 not configured (check R2_* env vars in .env)",
              file=sys.stderr)
        return 2

    if args.list:
        for k in _list_backups(client, settings.r2_bucket):
            print(k)
        return 0

    if not args.date:
        parser.error("date is required unless --list is passed")

    key = KEY_TEMPLATE.format(date=args.date)
    out = os.path.abspath(args.out)
    if os.path.exists(out):
        print(f"ERROR: refusing to overwrite existing file: {out}",
              file=sys.stderr)
        return 3

    with tempfile.NamedTemporaryFile(prefix="restore-", suffix=".db.gz",
                                     delete=False) as tmp:
        tmp_path = tmp.name
    try:
        print(f"downloading s3://{settings.r2_bucket}/{key} → {tmp_path}")
        client.download_file(settings.r2_bucket, key, tmp_path)
        print(f"decompressing → {out}")
        with gzip.open(tmp_path, "rb") as fin, open(out, "wb") as fout:
            while True:
                chunk = fin.read(1024 * 1024)
                if not chunk:
                    break
                fout.write(chunk)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    size = os.path.getsize(out)
    print(f"done — {out} ({size:,} bytes)")
    print("To swap in: stop service, "
          f"mv stock_dashboard.db stock_dashboard.db.bak && mv {out} stock_dashboard.db, "
          "restart service.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
