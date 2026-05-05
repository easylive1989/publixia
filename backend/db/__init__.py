"""Database package.

Public API kept stable via re-exports so call sites like
`from db import save_indicator` continue to work after the BE-B split.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from db.connection import (
    get_connection, DB_PATH, _memory_conn, _memory_lock,
)

logger = logging.getLogger(__name__)

_SEED_PATH = os.path.join(
    os.path.dirname(__file__), "..", "seeds", "auto_tracked_taiwan.txt",
)


def _seed_auto_tracked() -> None:
    """Idempotently load tickers from the seed file into auto_tracked_stocks.

    Strips inline `#` comments. Removed lines do NOT delete existing rows
    (monotonic policy)."""
    if not os.path.exists(_SEED_PATH):
        return
    from repositories.auto_tracked import insert_if_missing

    total = 0
    added = 0
    with open(_SEED_PATH, encoding="utf-8") as f:
        for line in f:
            ticker = line.split("#", 1)[0].strip()
            if not ticker:
                continue
            total += 1
            if insert_if_missing(ticker):
                added += 1
    logger.info("auto_tracked_seeded total=%d added=%d", total, added)


def init_db():
    """Bring the database up to the latest schema, then seed auto-tracked."""
    from db.runner import run_migrations
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    with get_connection() as conn:
        run_migrations(conn, migrations_dir)
    _seed_auto_tracked()


def purge_old_data(days: int = 1095):
    """Delete data older than `days`. Cross-table maintenance run weekly by scheduler."""
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat()
    cutoff_date = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_connection() as conn:
        conn.execute("DELETE FROM indicator_snapshots WHERE timestamp<?", (cutoff,))
        conn.execute("DELETE FROM stock_snapshots WHERE timestamp<?", (cutoff,))
        conn.execute("DELETE FROM stock_broker_daily WHERE date<?", (cutoff_date,))
        conn.execute("DELETE FROM stock_chip_daily WHERE date<?", (cutoff_date,))
        conn.execute("DELETE FROM stock_per_daily WHERE date<?", (cutoff_date,))
        conn.execute(
            "DELETE FROM stock_revenue_monthly "
            "WHERE (year * 12 + month) < (? * 12 + ?)",
            (int(cutoff_date[:4]), int(cutoff_date[5:7]))
        )
        conn.execute("DELETE FROM stock_financial_quarterly WHERE date<?", (cutoff_date,))
        # dividend not purged (long history important).
        # futures_daily not purged — long-history K-line is the main use case.


# Re-exports for backward compatibility.
from repositories.indicators import (  # noqa: E402,F401
    save_indicator, get_latest_indicator, get_indicator_history,
)
from repositories.stocks import (  # noqa: E402,F401
    save_stock_snapshot, get_latest_stock, get_watched_tickers,
    add_watched_ticker, remove_watched_ticker,
)
from repositories.alerts import (  # noqa: E402,F401
    list_alerts, add_alert, delete_alert, set_alert_enabled,
    get_active_alerts, mark_alert_triggered,
)
from repositories.chip import (  # noqa: E402,F401
    save_broker_daily_rows, get_broker_daily_range, get_latest_broker_date,
    save_chip_daily_rows, get_chip_daily_range, get_latest_chip_date,
)
from repositories.fundamentals import (  # noqa: E402,F401
    save_per_daily_rows, get_per_daily_range, get_latest_per_date,
    save_revenue_monthly_rows, get_revenue_monthly_range, get_latest_revenue_ym,
    save_financial_quarterly_rows, get_financial_quarterly_range, get_latest_financial_date,
    save_dividend_history_rows, get_dividend_history, get_latest_dividend_announce_date,
)
from repositories.futures import (  # noqa: E402,F401
    save_futures_daily_rows, get_futures_daily_range, get_latest_futures_date,
)
