"""market_breadth_daily repository：每日上市股票漲／跌／平盤家數。"""
from db.connection import get_connection


def upsert_days(market: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    payload = [{**row, "market": market} for row in rows]
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO market_breadth_daily "
            "(market, date, advancing, declining, unchanged) "
            "VALUES (:market, :date, :advancing, :declining, :unchanged) "
            "ON CONFLICT(market, date) DO UPDATE SET "
            "  advancing=excluded.advancing, declining=excluded.declining, "
            "  unchanged=excluded.unchanged, updated_at=datetime('now')",
            payload,
        )
    return len(payload)


def list_days(market: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, advancing, declining, unchanged "
            "FROM market_breadth_daily WHERE market = ? ORDER BY date",
            (market,),
        ).fetchall()
        return [dict(row) for row in rows]


def existing_dates(market: str) -> set[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date FROM market_breadth_daily WHERE market = ?",
            (market,),
        ).fetchall()
        return {row["date"] for row in rows}
