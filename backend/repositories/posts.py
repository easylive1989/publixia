"""Posts repository.

One row per scraped social post, deduped on ``(platform, platform_post_id)``.
``extraction_status`` drives the AI-extraction work queue
(pending → done|error|skipped).
"""
from db.connection import get_connection


def upsert_post(
    account_id: int,
    platform: str,
    platform_post_id: str,
    url: str,
    content: str,
    posted_at: str | None,
) -> tuple[int, bool]:
    """Insert a post, or update its content/url/posted_at if already seen.

    Returns ``(post_id, is_new)``. ``is_new`` is True only on first insert —
    the extraction runner uses it (combined with extracted trades) to decide
    whether to fire a Discord notification. An update intentionally leaves
    ``extraction_status`` untouched so re-scraping doesn't re-queue/re-notify.
    """
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM posts WHERE platform=? AND platform_post_id=?",
            (platform, platform_post_id),
        ).fetchone()
        if existing:
            post_id = existing["id"]
            conn.execute(
                "UPDATE posts SET content=?, url=?, posted_at=? WHERE id=?",
                (content, url, posted_at, post_id),
            )
            return post_id, False
        cur = conn.execute(
            "INSERT INTO posts ("
            "  account_id, platform, platform_post_id, url, content, posted_at"
            ") VALUES (?,?,?,?,?,?)",
            (account_id, platform, platform_post_id, url, content, posted_at),
        )
        return cur.lastrowid, True


def known_post_ids(account_id: int) -> frozenset[str]:
    """All platform_post_ids already stored for an account.

    The scraper uses this to detect when it has scrolled into already-seen
    posts and stop early (incremental runs).
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT platform_post_id FROM posts WHERE account_id=?",
            (account_id,),
        ).fetchall()
    return frozenset(r["platform_post_id"] for r in rows)


def list_pending_posts(limit: int = 20) -> list[dict]:
    """Posts awaiting AI extraction, oldest first.

    Includes ``error`` posts as retryable — extraction errors are usually
    transient (missing/!invalid AI credentials, a flaky response), so once the
    cause is fixed the next run reprocesses them. ``done``/``skipped`` are
    terminal.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, account_id, content, url FROM posts "
            "WHERE extraction_status IN ('pending','error') "
            "ORDER BY posted_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_stale_extraction_posts(current_version: str, limit: int = 20) -> list[dict]:
    """Already-extracted posts whose trades came from an older prompt version —
    re-extract them so a prompt improvement also cleans up past mistakes.
    (No-trade posts carry no version and are left alone — they have no bad data.)
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT p.id, p.account_id, p.content, p.url "
            "FROM posts p JOIN extracted_trades et ON et.post_id = p.id "
            "WHERE p.extraction_status='done' AND et.prompt_version != ? "
            "ORDER BY p.posted_at DESC LIMIT ?",
            (current_version, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def set_extraction_status(post_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE posts SET extraction_status=? WHERE id=?",
            (status, post_id),
        )


def list_recent_posts(limit: int = 50) -> list[dict]:
    """A single merged timeline across all enabled accounts (newest first),
    each post carrying its author (person_key / display_name / avatar). Trades
    are attached by the route via ``list_trades_for_posts``."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT p.id, p.platform, p.platform_post_id, p.url, p.content, "
            "       p.posted_at, p.extraction_status, "
            "       t.person_key, t.display_name, t.avatar_url "
            "FROM posts p "
            "JOIN tracked_accounts t ON t.id = p.account_id "
            "WHERE t.enabled=1 "
            "ORDER BY p.posted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_posts_for_person(person_key: str, limit: int = 50) -> list[dict]:
    """A person's posts (newest first) across all their handles, without
    trades attached — the route joins trades via ``list_trades_for_posts``."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT p.id, p.platform, p.platform_post_id, p.url, p.content, "
            "       p.posted_at, p.extraction_status "
            "FROM posts p "
            "JOIN tracked_accounts t ON t.id = p.account_id "
            "WHERE t.person_key=? "
            "ORDER BY p.posted_at DESC LIMIT ?",
            (person_key, limit),
        ).fetchall()
        return [dict(r) for r in rows]
