"""Database package.

Public API kept stable via re-exports so call sites like
`from db import save_indicator` continue to work without each module
having to know about repository layout.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from db.connection import (
    get_connection, DB_PATH, _memory_conn, _memory_lock,
)

logger = logging.getLogger(__name__)


def init_db():
    """Bring the database up to the latest schema."""
    from db.runner import run_migrations
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    with get_connection() as conn:
        run_migrations(conn, migrations_dir)


def purge_old_data(days: int = 1095):
    """Delete posts (and their cascaded trades) older than ``days``.

    Run weekly by the scheduler. ``extracted_trades`` rows are removed via
    the ON DELETE CASCADE foreign key on ``posts``.
    """
    cutoff = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    ).strftime("%Y-%m-%dT%H:%M:%S")
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM posts WHERE posted_at IS NOT NULL AND posted_at < ?", (cutoff,))
