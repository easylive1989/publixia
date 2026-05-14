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
    """Delete data older than `days`. Cross-table maintenance run weekly by scheduler.

    Only ``indicator_snapshots`` is purged today — all other surviving tables
    (futures, foreign_flow_ai_reports, institutional_*, txo_*, tx_large_trader)
    are intentionally kept long-term so the historical perspective on the
    dashboard isn't lost.
    """
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        conn.execute("DELETE FROM indicator_snapshots WHERE timestamp<?", (cutoff,))


# Re-exports for backward compatibility.
from repositories.indicators import (  # noqa: E402,F401
    save_indicator, get_latest_indicator, get_indicator_history,
)
from repositories.futures import (  # noqa: E402,F401
    save_futures_daily_rows, get_futures_daily_range, get_latest_futures_date,
)
