"""TAIFEX 大額交易人未沖銷部位結構表 repository (TX combined contract).

Backs the 散戶多空比 panel on `/futures/tw/foreign-flow`. Stores the
daily TAIFEX large-trader OI structure for the 臺股期貨 entry
(TX + MTX/4 + TMF/20, 全部月份合計).
"""
from db.connection import get_connection


def save_large_trader_rows(rows: list[dict]) -> None:
    """Bulk upsert daily TX large-trader rows.

    Each row needs: date, market_oi, top5_long_oi, top5_short_oi,
    top10_long_oi, top10_short_oi.
    """
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO tx_large_trader_daily ("
            "  date, market_oi, top5_long_oi, top5_short_oi, "
            "  top10_long_oi, top10_short_oi"
            ") VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET "
            "  market_oi      = excluded.market_oi, "
            "  top5_long_oi   = excluded.top5_long_oi, "
            "  top5_short_oi  = excluded.top5_short_oi, "
            "  top10_long_oi  = excluded.top10_long_oi, "
            "  top10_short_oi = excluded.top10_short_oi",
            [
                (
                    r["date"],
                    int(r.get("market_oi")      or 0),
                    int(r.get("top5_long_oi")   or 0),
                    int(r.get("top5_short_oi")  or 0),
                    int(r.get("top10_long_oi")  or 0),
                    int(r.get("top10_short_oi") or 0),
                )
                for r in rows
            ],
        )


def get_large_trader_range(since_date: str) -> list[dict]:
    """Rows on or after since_date (YYYY-MM-DD), ascending."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, market_oi, top5_long_oi, top5_short_oi, "
            "       top10_long_oi, top10_short_oi "
            "FROM tx_large_trader_daily "
            "WHERE date>=? ORDER BY date",
            (since_date,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_large_trader_date() -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM tx_large_trader_daily",
        ).fetchone()
        return row["d"] if row and row["d"] else None
