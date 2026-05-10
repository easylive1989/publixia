"""Three-major-investor options-positions repository.

Backs the options block of the `/futures/tw/foreign-flow` page. Mirrors
`institutional_futures` but keyed on the broader 4-tuple
`(symbol, date, identity, put_call)` so a single day produces 6 rows
(3 identities × CALL/PUT) per product.

Source: TAIFEX `三大法人 - 選擇權買賣權分計` daily CSV. Amounts kept in
千元 to match `institutional_futures_daily`; presentation-time conversion
to 億元 happens in the frontend.
"""
from db.connection import get_connection


def save_institutional_options_rows(rows: list[dict]) -> None:
    """Bulk upsert daily options-position rows.

    Each row needs: symbol, date, identity, put_call, long_oi, short_oi,
    long_amount, short_amount.
    """
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO institutional_options_daily ("
            "  symbol, date, identity, put_call, "
            "  long_oi, short_oi, long_amount, short_amount"
            ") VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(symbol, date, identity, put_call) DO UPDATE SET "
            "  long_oi      = excluded.long_oi, "
            "  short_oi     = excluded.short_oi, "
            "  long_amount  = excluded.long_amount, "
            "  short_amount = excluded.short_amount",
            [
                (
                    r["symbol"], r["date"],
                    r["identity"], r["put_call"],
                    int(r.get("long_oi")  or 0),
                    int(r.get("short_oi") or 0),
                    float(r.get("long_amount")  or 0.0),
                    float(r.get("short_amount") or 0.0),
                )
                for r in rows
            ],
        )


def get_institutional_options_range(
    symbol: str, since_date: str,
) -> list[dict]:
    """All rows for symbol on or after since_date (YYYY-MM-DD), ascending."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, identity, put_call, "
            "       long_oi, short_oi, long_amount, short_amount "
            "FROM institutional_options_daily "
            "WHERE symbol=? AND date>=? "
            "ORDER BY date, identity, put_call",
            (symbol, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_institutional_options_date(symbol: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM institutional_options_daily "
            "WHERE symbol=?",
            (symbol,),
        ).fetchone()
        return row["d"] if row and row["d"] else None
