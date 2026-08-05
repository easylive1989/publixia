"""market_volume_daily repository: 各市場的每日「指數收盤 + 量能」原始列.

每個查詢都要指定 ``market``（``core.markets`` 的 TW/US）—— 兩個市場的交易日曆
與 turnover 單位都不同，混在一起迴歸沒有意義，所以沒有「全部市場」的取法。
"""
from db.connection import get_connection


def upsert_days(market: str, rows: list[dict]) -> int:
    """Upsert on (market, date). Returns rows written."""
    if not rows:
        return 0
    payload = [{**r, "market": market} for r in rows]
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO market_volume_daily (market, date, index_close, turnover) "
            "VALUES (:market, :date, :index_close, :turnover) "
            "ON CONFLICT(market, date) DO UPDATE SET "
            "  index_close=excluded.index_close, turnover=excluded.turnover, "
            "  updated_at=datetime('now')",
            payload,
        )
    return len(payload)


def list_days(market: str) -> list[dict]:
    """該市場的所有列，舊 → 新（market_heat 計算所需的順序）。"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, index_close, turnover FROM market_volume_daily "
            "WHERE market = ? ORDER BY date",
            (market,),
        ).fetchall()
        return [dict(r) for r in rows]


def latest_date(market: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM market_volume_daily WHERE market = ?",
            (market,),
        ).fetchone()
        return row["d"]
