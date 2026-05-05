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
    if str(path) == ":memory:":
        # Test path: share backend's cached :memory: connection so admin
        # code and backend code see the same database within a pytest run.
        import sys
        backend_dir = str(_REPO_ROOT / "backend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from db.connection import get_connection as _backend_conn  # type: ignore
        return _backend_conn()
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found at {path}. Set DB_PATH or copy the SQLite "
            f"file to {_DEFAULT_DB}."
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
