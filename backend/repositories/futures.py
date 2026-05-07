"""Taiwan index futures (TX) daily OHLCV repository."""
from db.connection import get_connection


def save_futures_daily_rows(rows: list[dict]) -> None:
    """Upsert OHLCV rows keyed on (symbol, date)."""
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO futures_daily ("
            "  symbol, date, contract_date, open, high, low, close, "
            "  volume, open_interest, settlement"
            ") VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(symbol, date) DO UPDATE SET "
            "  contract_date=excluded.contract_date, "
            "  open=excluded.open, high=excluded.high, low=excluded.low, "
            "  close=excluded.close, volume=excluded.volume, "
            "  open_interest=excluded.open_interest, "
            "  settlement=excluded.settlement",
            [
                (
                    r["symbol"], r["date"], r.get("contract_date"),
                    r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                    r.get("volume"), r.get("open_interest"), r.get("settlement"),
                )
                for r in rows
            ],
        )


def get_futures_daily_range(symbol: str, since_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume, open_interest "
            "FROM futures_daily WHERE symbol=? AND date>=? "
            "ORDER BY date",
            (symbol, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_futures_bar(symbol: str) -> dict | None:
    """Return the most recent OHLCV row for the symbol, or None if empty.
    Used by force_close to pick a fill price without scanning history."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT date, open, high, low, close, volume, open_interest "
            "FROM futures_daily WHERE symbol=? ORDER BY date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        return dict(row) if row else None


def get_latest_futures_date(symbol: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM futures_daily WHERE symbol=?",
            (symbol,),
        ).fetchone()
        return row["d"] if row and row["d"] else None
