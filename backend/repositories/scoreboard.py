"""Scoreboard repository.

One flat query of every enabled person's trades with the one performance metric
the scoreboard grades on — ``pct_latest`` (current return since the call). The
aggregation/scoring lives in ``services/scoreboard.py`` so the rule is testable
in isolation.
"""
from db.connection import get_connection


def list_scored_trades() -> list[dict]:
    """Every trade of every enabled person, newest first, with its latest
    return. ``pct_latest`` is NULL until price tracking has a base price.

    Rows: ``person_key, direction, pct_latest, posted_at``.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT t.person_key, et.direction, tpt.pct_latest, p.posted_at "
            "FROM extracted_trades et "
            "JOIN posts p ON p.id = et.post_id "
            "JOIN tracked_accounts t ON t.id = p.account_id "
            "LEFT JOIN trade_price_tracking tpt "
            "  ON tpt.post_id = et.post_id AND tpt.ticker = et.ticker "
            "WHERE t.enabled = 1 "
            "ORDER BY p.posted_at DESC, et.id DESC"
        ).fetchall()
    return [dict(r) for r in rows]
