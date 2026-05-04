"""Broker + chip per-day repository."""
from db.connection import get_connection


# --- Broker (per-trader-per-day) ---

def save_broker_daily_rows(rows: list[dict]) -> None:
    """Bulk upsert per-broker per-day aggregates.

    Each row needs: ticker, date, securities_trader_id, securities_trader,
    buy_volume, sell_volume, buy_amount, sell_amount.
    """
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_broker_daily "
            "(ticker, date, securities_trader_id, securities_trader, "
            " buy_volume, sell_volume, buy_amount, sell_amount) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, date, securities_trader_id) DO UPDATE SET "
            " securities_trader=excluded.securities_trader, "
            " buy_volume=excluded.buy_volume, "
            " sell_volume=excluded.sell_volume, "
            " buy_amount=excluded.buy_amount, "
            " sell_amount=excluded.sell_amount",
            [
                (
                    r["ticker"], r["date"], r["securities_trader_id"],
                    r.get("securities_trader") or "",
                    r.get("buy_volume", 0) or 0,
                    r.get("sell_volume", 0) or 0,
                    r.get("buy_amount", 0) or 0,
                    r.get("sell_amount", 0) or 0,
                )
                for r in rows
            ],
        )


def get_broker_daily_range(ticker: str, since_date: str) -> list[dict]:
    """Return per-broker daily aggregates for ticker on or after since_date (YYYY-MM-DD)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, securities_trader_id, securities_trader, "
            "       buy_volume, sell_volume, buy_amount, sell_amount "
            "FROM stock_broker_daily "
            "WHERE ticker=? AND date>=? "
            "ORDER BY date",
            (ticker, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_broker_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_broker_daily WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None


# --- Chip (per-day aggregated) ---

def save_chip_daily_rows(rows: list[dict]) -> None:
    """Bulk upsert per-day stock chip rows."""
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_chip_daily "
            "(ticker, date, foreign_buy, foreign_sell, trust_buy, trust_sell, "
            " dealer_buy, dealer_sell, margin_balance, short_balance) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, date) DO UPDATE SET "
            " foreign_buy=COALESCE(excluded.foreign_buy, foreign_buy), "
            " foreign_sell=COALESCE(excluded.foreign_sell, foreign_sell), "
            " trust_buy=COALESCE(excluded.trust_buy, trust_buy), "
            " trust_sell=COALESCE(excluded.trust_sell, trust_sell), "
            " dealer_buy=COALESCE(excluded.dealer_buy, dealer_buy), "
            " dealer_sell=COALESCE(excluded.dealer_sell, dealer_sell), "
            " margin_balance=COALESCE(excluded.margin_balance, margin_balance), "
            " short_balance=COALESCE(excluded.short_balance, short_balance)",
            [
                (r["ticker"], r["date"],
                 r.get("foreign_buy"), r.get("foreign_sell"),
                 r.get("trust_buy"), r.get("trust_sell"),
                 r.get("dealer_buy"), r.get("dealer_sell"),
                 r.get("margin_balance"), r.get("short_balance"))
                for r in rows
            ],
        )


def get_chip_daily_range(ticker: str, since_date: str) -> list[dict]:
    """Per-day chip rows for ticker on or after since_date (YYYY-MM-DD)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, foreign_buy, foreign_sell, trust_buy, trust_sell, "
            "       dealer_buy, dealer_sell, margin_balance, short_balance "
            "FROM stock_chip_daily WHERE ticker=? AND date>=? ORDER BY date",
            (ticker, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_chip_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_chip_daily WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None
