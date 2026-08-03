"""market_volume_daily repository: TWSE 大盤成交統計原始列."""
from db.connection import get_connection


def upsert_days(rows: list[dict]) -> int:
    """Upsert on date. Returns rows written."""
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO market_volume_daily (date, taiex_close, turnover) "
            "VALUES (:date, :taiex_close, :turnover) "
            "ON CONFLICT(date) DO UPDATE SET "
            "  taiex_close=excluded.taiex_close, turnover=excluded.turnover, "
            "  updated_at=datetime('now')",
            rows,
        )
    return len(rows)


def list_days() -> list[dict]:
    """All rows, oldest → newest (the order market_heat computes in)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, taiex_close, turnover "
            "FROM market_volume_daily ORDER BY date",
        ).fetchall()
        return [dict(r) for r in rows]


def latest_date() -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM market_volume_daily",
        ).fetchone()
        return row["d"]
