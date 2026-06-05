"""trade_price_tracking repository: post×stock price-window rows."""
from db.connection import get_connection


def list_tracking_targets() -> list[dict]:
    """Distinct (post_id, ticker, market, posted_at) needing computation —
    no tracking row yet, or a row whose window hasn't finished (status != done).
    Only mapped tickers with a known post time."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT et.post_id, et.ticker, et.market, p.posted_at "
            "FROM extracted_trades et "
            "JOIN posts p ON p.id = et.post_id "
            "LEFT JOIN trade_price_tracking t "
            "  ON t.post_id = et.post_id AND t.ticker = et.ticker "
            "WHERE et.ticker IS NOT NULL AND p.posted_at IS NOT NULL "
            "  AND (t.id IS NULL OR t.status != 'done') "
            "ORDER BY p.posted_at DESC",
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_tracking(post_id: int, ticker: str, market: str, w: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO trade_price_tracking ("
            "  post_id, ticker, market, base_date, base_price, "
            "  price_7d, price_1m, price_latest, latest_date, "
            "  pct_7d, pct_1m, pct_latest, status"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(post_id, ticker) DO UPDATE SET "
            "  market=excluded.market, base_date=excluded.base_date, "
            "  base_price=excluded.base_price, price_7d=excluded.price_7d, "
            "  price_1m=excluded.price_1m, price_latest=excluded.price_latest, "
            "  latest_date=excluded.latest_date, pct_7d=excluded.pct_7d, "
            "  pct_1m=excluded.pct_1m, pct_latest=excluded.pct_latest, "
            "  status=excluded.status, updated_at=datetime('now')",
            (
                post_id, ticker, market,
                w["base_date"], w["base_price"],
                w["price_7d"], w["price_1m"], w["price_latest"], w["latest_date"],
                w["pct_7d"], w["pct_1m"], w["pct_latest"],
                w["status"],
            ),
        )
