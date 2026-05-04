"""SQLite connection for the admin CLI.

Path is resolved from the DB_PATH env var, falling back to
<repo_root>/backend/stock_dashboard.db so the tool works out of the box
when run against a local checkout.
"""
import os
import sqlite3
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = _REPO_ROOT / "backend" / "stock_dashboard.db"


def db_path() -> Path:
    raw = os.environ.get("DB_PATH")
    return Path(raw).expanduser() if raw else _DEFAULT_DB


def connect() -> sqlite3.Connection:
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found at {path}. Set DB_PATH or copy the SQLite "
            f"file to {_DEFAULT_DB}."
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
