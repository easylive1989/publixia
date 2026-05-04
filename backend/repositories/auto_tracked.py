"""Auto-tracked stocks repository (Taiwan top-100, monotonic)."""
from db.connection import get_connection


def insert_if_missing(ticker: str, source: str = 'twse-top100') -> bool:
    """INSERT OR IGNORE; returns True if a new row was inserted."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO auto_tracked_stocks (ticker, source) "
            "VALUES (?, ?)",
            (ticker, source),
        )
        return cur.rowcount > 0


def list_auto_tracked_tickers() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ticker FROM auto_tracked_stocks ORDER BY ticker"
        ).fetchall()
        return [r["ticker"] for r in rows]


def is_auto_tracked(ticker: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM auto_tracked_stocks WHERE ticker = ? LIMIT 1",
            (ticker,),
        ).fetchone()
        return row is not None
