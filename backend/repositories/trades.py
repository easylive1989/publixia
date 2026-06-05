"""Extracted-trades repository.

Zero-to-many trade signals per post (the AI extraction output). Upsert keyed
on ``(post_id, raw_symbol, direction)`` so re-extracting a post is idempotent.
"""
from db.connection import get_connection


def save_trades(
    post_id: int,
    trades: list[dict],
    model: str,
    prompt_version: str,
) -> int:
    """Upsert the trades extracted from one post.

    Each trade dict carries: ``raw_symbol``, ``direction`` (required),
    and optional ``ticker``, ``market``, ``price``, ``quantity``,
    ``trade_date``, ``confidence``. Returns the number of rows written.

    **Replace semantics**: the post's existing trades are deleted first, so
    re-extracting a post (e.g. with a newer prompt) cleanly drops symbols the
    new run no longer reports — not just upserts the ones it does.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM extracted_trades WHERE post_id=?", (post_id,))
        for t in trades:
            conn.execute(
                "INSERT INTO extracted_trades ("
                "  post_id, raw_symbol, ticker, market, direction, "
                "  price, quantity, trade_date, confidence, model, prompt_version"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(post_id, raw_symbol, direction) DO UPDATE SET "
                "  ticker         = excluded.ticker, "
                "  market         = excluded.market, "
                "  price          = excluded.price, "
                "  quantity       = excluded.quantity, "
                "  trade_date     = excluded.trade_date, "
                "  confidence     = excluded.confidence, "
                "  model          = excluded.model, "
                "  prompt_version = excluded.prompt_version",
                (
                    post_id,
                    t["raw_symbol"],
                    t.get("ticker"),
                    t.get("market"),
                    t["direction"],
                    t.get("price"),
                    t.get("quantity"),
                    t.get("trade_date"),
                    float(t.get("confidence", 0.0)),
                    model,
                    prompt_version,
                ),
            )
    return len(trades)


def has_existing_trades(post_id: int) -> bool:
    """Whether a post already has any extracted trades — used by the runner to
    avoid re-notifying Discord when a post is re-extracted."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM extracted_trades WHERE post_id=? LIMIT 1", (post_id,)
        ).fetchone()
    return row is not None


def list_trades_for_posts(post_ids: list[int]) -> dict[int, list[dict]]:
    """Map post_id → its trades, for assembling the person timeline payload."""
    if not post_ids:
        return {}
    placeholders = ",".join("?" for _ in post_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT et.post_id, et.raw_symbol, et.ticker, et.market, et.direction, "
            f"       et.price, et.quantity, et.trade_date, et.confidence, "
            f"       sr.canonical_name AS stock_name, "
            f"       tpt.pct_7d, tpt.pct_1m, tpt.base_price, tpt.status AS price_status "
            f"FROM extracted_trades et "
            f"LEFT JOIN stock_reference sr "
            f"  ON sr.market = et.market AND sr.ticker = et.ticker "
            f"LEFT JOIN trade_price_tracking tpt "
            f"  ON tpt.post_id = et.post_id AND tpt.ticker = et.ticker "
            f"WHERE et.post_id IN ({placeholders}) "
            f"ORDER BY et.id",
            tuple(post_ids),
        ).fetchall()
    out: dict[int, list[dict]] = {pid: [] for pid in post_ids}
    for r in rows:
        d = dict(r)
        out.setdefault(d["post_id"], []).append(d)
    return out
