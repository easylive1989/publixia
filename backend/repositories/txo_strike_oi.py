"""Market-wide TXO open interest per 履約價 (strike) repository.

Backs the 各履約價未平倉量分布 chart on the foreign-futures page. Stores
the TAIFEX 選擇權每日交易行情 download row-per-(date, expiry, strike,
CALL/PUT). Unlike institutional_options_daily, there is no identity
dimension — TAIFEX only publishes strike-level OI as a market total.
"""
from db.connection import get_connection


def save_txo_strike_oi_rows(rows: list[dict]) -> None:
    """Bulk upsert per-strike OI rows.

    Each row needs: symbol, date, expiry_month, strike, put_call,
    open_interest, settle_price (settle_price may be None).
    """
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO txo_strike_oi_daily ("
            "  symbol, date, expiry_month, strike, put_call,"
            "  open_interest, settle_price"
            ") VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(symbol, date, expiry_month, strike, put_call) "
            "DO UPDATE SET "
            "  open_interest = excluded.open_interest, "
            "  settle_price  = excluded.settle_price",
            [
                (
                    r["symbol"], r["date"],
                    r["expiry_month"], float(r["strike"]),
                    r["put_call"],
                    int(r.get("open_interest") or 0),
                    (
                        None
                        if r.get("settle_price") in (None, "")
                        else float(r["settle_price"])
                    ),
                )
                for r in rows
            ],
        )


def get_txo_strike_oi_on_date(
    symbol: str, date: str,
) -> list[dict]:
    """All strike/CALL/PUT rows for a single date, ascending by strike."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, expiry_month, strike, put_call, "
            "       open_interest, settle_price "
            "FROM txo_strike_oi_daily "
            "WHERE symbol=? AND date=? "
            "ORDER BY expiry_month, strike, put_call",
            (symbol, date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_txo_strike_oi_dates(
    symbol: str, since_date: str,
) -> list[str]:
    """Distinct trading dates that have strike-OI rows, ascending."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM txo_strike_oi_daily "
            "WHERE symbol=? AND date>=? ORDER BY date",
            (symbol, since_date),
        ).fetchall()
        return [r["date"] for r in rows]


def get_latest_txo_strike_oi_date(symbol: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM txo_strike_oi_daily WHERE symbol=?",
            (symbol,),
        ).fetchone()
        return row["d"] if row and row["d"] else None
