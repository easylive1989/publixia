"""Database package.

Public API kept stable via re-exports so call sites like
`from db import save_indicator` continue to work without each module
having to know about repository layout.
"""
import logging
import os

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
