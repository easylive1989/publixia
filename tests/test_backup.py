"""Backup service tests — hot backup correctness + retention policy."""
from __future__ import annotations

import gzip
import os
import sqlite3
from datetime import date
from unittest.mock import MagicMock

import pytest

from services import backup as backup_mod


def _make_sqlite_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t VALUES ('hello', 'world')")
    conn.commit()
    conn.close()


def test_hot_backup_then_gzip_roundtrip(tmp_path):
    src = tmp_path / "src.db"
    snap = tmp_path / "snap.db"
    gz = tmp_path / "snap.db.gz"
    _make_sqlite_db(str(src))

    backup_mod._hot_backup(str(src), str(snap))
    backup_mod._gzip_file(str(snap), str(gz))

    # Decompress and verify the snapshot is a real, queryable SQLite file
    # with the original row intact.
    restored = tmp_path / "restored.db"
    with gzip.open(gz, "rb") as fin, open(restored, "wb") as fout:
        fout.write(fin.read())
    conn = sqlite3.connect(str(restored))
    rows = conn.execute("SELECT k, v FROM t").fetchall()
    conn.close()
    assert rows == [("hello", "world")]


@pytest.mark.parametrize("name,today,expected", [
    # Within 30-day window: keep.
    ("db/stock_dashboard-2026-05-01.db.gz", date(2026, 5, 10), True),
    ("db/stock_dashboard-2026-04-15.db.gz", date(2026, 5, 10), True),  # 25 days old
    ("db/stock_dashboard-2026-04-10.db.gz", date(2026, 5, 10), True),  # exactly 30
    # Past 30 days, not month-1: drop.
    ("db/stock_dashboard-2026-04-09.db.gz", date(2026, 5, 10), False),  # 31 days, day != 1
    ("db/stock_dashboard-2026-03-15.db.gz", date(2026, 5, 10), False),
    # Past 30 days, month-1, within 1y: keep.
    ("db/stock_dashboard-2026-04-01.db.gz", date(2026, 5, 10), True),
    ("db/stock_dashboard-2025-06-01.db.gz", date(2026, 5, 10), True),
    # Past 1y even on month-1: drop.
    ("db/stock_dashboard-2025-04-01.db.gz", date(2026, 5, 10), False),  # >365 days
])
def test_should_keep_retention_policy(name, today, expected):
    assert backup_mod._should_keep(name, today) is expected


def test_should_keep_unexpected_key_is_kept():
    # Foreign objects in the bucket shouldn't be deleted by us.
    assert backup_mod._should_keep("db/something-else.txt", date(2026, 5, 10)) is True


def test_prune_deletes_only_expired(monkeypatch):
    today = date(2026, 5, 10)
    keys = [
        "db/stock_dashboard-2026-05-01.db.gz",  # keep (recent)
        "db/stock_dashboard-2026-04-09.db.gz",  # drop (31d, not 1st)
        "db/stock_dashboard-2026-04-01.db.gz",  # keep (1st-of-month)
        "db/stock_dashboard-2025-04-01.db.gz",  # drop (>1y)
    ]
    client = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"Contents": [{"Key": k} for k in keys]},
    ]
    client.get_paginator.return_value = paginator
    client.delete_objects.return_value = {
        "Deleted": [
            {"Key": "db/stock_dashboard-2026-04-09.db.gz"},
            {"Key": "db/stock_dashboard-2025-04-01.db.gz"},
        ]
    }

    n = backup_mod._prune(client, "bucket", today)

    assert n == 2
    client.delete_objects.assert_called_once()
    deleted_keys = {
        o["Key"] for o in client.delete_objects.call_args.kwargs["Delete"]["Objects"]
    }
    assert deleted_keys == {
        "db/stock_dashboard-2026-04-09.db.gz",
        "db/stock_dashboard-2025-04-01.db.gz",
    }


def test_backup_skips_silently_when_unconfigured(monkeypatch, caplog):
    monkeypatch.setattr(backup_mod, "_r2_client", lambda: None)
    with caplog.at_level("WARNING"):
        ok = backup_mod.backup_db_to_r2()
    assert ok is True
    assert any("backup_skipped" in r.message for r in caplog.records)


def test_backup_uploads_then_prunes(monkeypatch, tmp_path):
    src = tmp_path / "stock_dashboard.db"
    _make_sqlite_db(str(src))
    monkeypatch.setattr(backup_mod.settings, "db_path", str(src))

    client = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": []}]
    client.get_paginator.return_value = paginator
    monkeypatch.setattr(backup_mod, "_r2_client", lambda: client)
    monkeypatch.setattr(backup_mod.settings, "r2_bucket", "test-bucket")

    ok = backup_mod.backup_db_to_r2()
    assert ok is True

    # Verify upload was called once, with a key matching today's date format.
    client.upload_file.assert_called_once()
    args = client.upload_file.call_args
    local_path, bucket, key = args.args
    assert bucket == "test-bucket"
    assert key.startswith("db/stock_dashboard-") and key.endswith(".db.gz")
    # The temp file should be gone (temp dir auto-cleaned by ctx manager).
    assert not os.path.exists(local_path)
