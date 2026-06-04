"""Tracked-account repository.

A row is one social handle of one person. ``person_key`` groups multiple
handles/platforms under the same person, so the public "people" views
aggregate by ``person_key`` (today every person has a single Threads handle,
but the model is data-driven so FB or a second handle can be added later).
"""
from db.connection import get_connection

_ACCOUNT_COLS = (
    "id, person_key, display_name, platform, handle, profile_url, "
    "enabled, session_cookie, backfill_months, avatar_url"
)


def list_accounts(enabled_only: bool = True) -> list[dict]:
    """All tracked handles. Used by the scraper runner."""
    sql = f"SELECT {_ACCOUNT_COLS} FROM tracked_accounts"
    if enabled_only:
        sql += " WHERE enabled=1"
    sql += " ORDER BY id"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def get_account(account_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_ACCOUNT_COLS} FROM tracked_accounts WHERE id=?",
            (account_id,),
        ).fetchone()
        return dict(row) if row else None


def list_people_with_stats() -> list[dict]:
    """One row per person (grouped by ``person_key``) with summary stats for
    the home cards: platforms, latest post time, total extracted trades."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT t.person_key, "
            "       MIN(t.display_name) AS display_name, "
            "       MAX(t.avatar_url)   AS avatar_url, "
            "       GROUP_CONCAT(DISTINCT t.platform) AS platforms, "
            "       MAX(p.posted_at)    AS latest_post_at, "
            "       COUNT(DISTINCT tr.id) AS trade_count "
            "FROM tracked_accounts t "
            "LEFT JOIN posts p ON p.account_id = t.id "
            "LEFT JOIN extracted_trades tr ON tr.post_id = p.id "
            "WHERE t.enabled=1 "
            "GROUP BY t.person_key "
            "ORDER BY latest_post_at DESC"
        ).fetchall()
    return [
        {
            "person_key": r["person_key"],
            "display_name": r["display_name"],
            "avatar_url": r["avatar_url"],
            "platforms": (r["platforms"] or "").split(",") if r["platforms"] else [],
            "latest_post_at": r["latest_post_at"],
            "trade_count": r["trade_count"],
        }
        for r in rows
    ]


def get_person(person_key: str) -> dict | None:
    """Profile header: display name + the person's handles. ``None`` if the
    person_key has no enabled accounts."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT display_name, platform, handle, profile_url, avatar_url "
            "FROM tracked_accounts WHERE person_key=? AND enabled=1 ORDER BY id",
            (person_key,),
        ).fetchall()
    if not rows:
        return None
    return {
        "person_key": person_key,
        "display_name": rows[0]["display_name"],
        "avatar_url": rows[0]["avatar_url"],
        "accounts": [
            {
                "platform": r["platform"],
                "handle": r["handle"],
                "profile_url": r["profile_url"],
            }
            for r in rows
        ],
    }
