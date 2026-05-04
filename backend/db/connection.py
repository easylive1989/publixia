"""Connection factory + in-memory singleton for tests.

Kept dependency-free so repositories can import this without triggering
circular imports through db/__init__.py's re-exports.
"""
import sqlite3
import threading

from core.settings import settings

DB_PATH = settings.db_path
_memory_conn = None
_memory_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    global _memory_conn
    if DB_PATH == ":memory:":
        with _memory_lock:
            if _memory_conn is None:
                _memory_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
                _memory_conn.row_factory = sqlite3.Row
        return _memory_conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
