"""Foreign-investor futures positions repository.

Backs the `/futures/tw/foreign-flow` page. Two tables:

- `institutional_futures_daily` — per-symbol daily snapshot of foreign
  long/short open-interest lots and contract amounts. Source: TAIFEX
  `三大法人 - 區分各期貨契約` daily CSV.
- `futures_settlement_dates` — final-settlement date per contract month.
  Source: TAIFEX `期貨契約最後交易日` page (with an algorithmic fallback
  for when scraping fails — third Wednesday of the calendar month).
"""
from db.connection import get_connection


# ── institutional_futures_daily ────────────────────────────────────────

def save_institutional_futures_rows(rows: list[dict]) -> None:
    """Bulk upsert daily TX/MTX foreign-position rows.

    Each row needs: symbol, date, foreign_long_oi, foreign_short_oi,
    foreign_long_amount, foreign_short_amount.
    """
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO institutional_futures_daily ("
            "  symbol, date, foreign_long_oi, foreign_short_oi, "
            "  foreign_long_amount, foreign_short_amount"
            ") VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(symbol, date) DO UPDATE SET "
            "  foreign_long_oi      = excluded.foreign_long_oi, "
            "  foreign_short_oi     = excluded.foreign_short_oi, "
            "  foreign_long_amount  = excluded.foreign_long_amount, "
            "  foreign_short_amount = excluded.foreign_short_amount",
            [
                (
                    r["symbol"], r["date"],
                    int(r.get("foreign_long_oi")  or 0),
                    int(r.get("foreign_short_oi") or 0),
                    float(r.get("foreign_long_amount")  or 0.0),
                    float(r.get("foreign_short_amount") or 0.0),
                )
                for r in rows
            ],
        )


def get_institutional_futures_range(
    symbol: str, since_date: str,
) -> list[dict]:
    """All rows for symbol on or after since_date (YYYY-MM-DD), ascending."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, foreign_long_oi, foreign_short_oi, "
            "       foreign_long_amount, foreign_short_amount "
            "FROM institutional_futures_daily "
            "WHERE symbol=? AND date>=? ORDER BY date",
            (symbol, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_institutional_futures_date(symbol: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM institutional_futures_daily "
            "WHERE symbol=?",
            (symbol,),
        ).fetchone()
        return row["d"] if row and row["d"] else None


# ── futures_settlement_dates ───────────────────────────────────────────

def save_settlement_dates(symbol: str, items: list[dict]) -> None:
    """Bulk upsert {year_month: 'YYYY-MM', settlement_date: 'YYYY-MM-DD'}."""
    if not items:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO futures_settlement_dates "
            "(symbol, year_month, settlement_date) VALUES (?, ?, ?) "
            "ON CONFLICT(symbol, year_month) DO UPDATE SET "
            "  settlement_date = excluded.settlement_date",
            [(symbol, it["year_month"], it["settlement_date"]) for it in items],
        )


def get_settlement_dates_in_range(
    symbol: str, start_date: str, end_date: str,
) -> list[str]:
    """Settlement dates for `symbol` falling inside [start_date, end_date]."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT settlement_date FROM futures_settlement_dates "
            "WHERE symbol=? AND settlement_date BETWEEN ? AND ? "
            "ORDER BY settlement_date",
            (symbol, start_date, end_date),
        ).fetchall()
        return [r["settlement_date"] for r in rows]
