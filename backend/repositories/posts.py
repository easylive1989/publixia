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
    audio_url: str | None = None,
    transcript_url: str | None = None,
    title: str | None = None,
) -> tuple[int, bool]:
    """Insert a post, or update its content/url/posted_at if already seen.

    Returns ``(post_id, is_new)``. ``is_new`` is True only on first insert —
    the extraction runner uses it (combined with extracted trades) to decide
    whether to fire a Discord notification. An update intentionally leaves
    ``extraction_status`` untouched so re-scraping doesn't re-queue/re-notify.

    Podcast posts (``audio_url`` set) seed ``transcript_status='pending'`` so the
    transcription job picks them up; text platforms leave it NULL so extraction
    runs immediately. On update, ``content`` is only overwritten when the incoming
    value is non-empty — a re-scraped podcast carries an empty placeholder and must
    not wipe an already-stored transcript — and ``transcript_status`` is left as-is
    so re-scraping doesn't re-transcribe.
    """
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM posts WHERE platform=? AND platform_post_id=?",
            (platform, platform_post_id),
        ).fetchone()
        if existing:
            post_id = existing["id"]
            if content:
                conn.execute(
                    "UPDATE posts SET content=?, url=?, posted_at=?, title=? WHERE id=?",
                    (content, url, posted_at, title, post_id),
                )
            else:
                conn.execute(
                    "UPDATE posts SET url=?, posted_at=?, title=? WHERE id=?",
                    (url, posted_at, title, post_id),
                )
            return post_id, False
        transcript_status = "pending" if audio_url else None
        cur = conn.execute(
            "INSERT INTO posts ("
            "  account_id, platform, platform_post_id, url, content, posted_at,"
            "  audio_url, transcript_url, transcript_status, title"
            ") VALUES (?,?,?,?,?,?,?,?,?,?)",
            (account_id, platform, platform_post_id, url, content, posted_at,
             audio_url, transcript_url, transcript_status, title),
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

    The ``transcript_status`` gate keeps podcast posts out of the queue until
    their audio has been transcribed (content filled). Text posts have a NULL
    ``transcript_status`` and are eligible immediately.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, account_id, content, url FROM posts "
            "WHERE extraction_status IN ('pending','error') "
            "  AND (transcript_status IS NULL OR transcript_status='done') "
            "ORDER BY posted_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_stale_extraction_posts(current_version: str, limit: int = 20) -> list[dict]:
    """``done`` posts extracted by an older prompt version — re-extract them so
    a prompt improvement also fixes past results. Keyed on ``posts``'
    ``extraction_version`` (not trades), so posts wrongly extracted as *empty*
    are caught too. Legacy rows with NULL version count as stale.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, account_id, content, url FROM posts "
            "WHERE extraction_status='done' "
            "  AND (extraction_version IS NULL OR extraction_version != ?) "
            "  AND (transcript_status IS NULL OR transcript_status='done') "
            "ORDER BY posted_at DESC LIMIT ?",
            (current_version, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def set_extraction_status(post_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE posts SET extraction_status=? WHERE id=?",
            (status, post_id),
        )


def list_pending_transcription_posts(limit: int = 5) -> list[dict]:
    """Podcast posts awaiting transcription, **newest first** — the freshest
    episode carries the most actionable signal, and on a first-time backfill we
    want the latest episode transcribed before older ones. ``error`` is retried
    (download/ffmpeg/Groq failures are usually transient). The lower default
    ``limit`` reflects that transcription is heavier (audio download + ffmpeg +
    Groq rate limits) than text extraction.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, audio_url, transcript_url FROM posts "
            "WHERE transcript_status IN ('pending','error') "
            "ORDER BY posted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def set_transcript_status(post_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE posts SET transcript_status=? WHERE id=?",
            (status, post_id),
        )


def set_post_transcript(post_id: int, content: str, source: str) -> None:
    """Store a transcript as the post's content and mark transcription done.

    Leaves ``extraction_status`` as 'pending' so the post now passes the queue
    gate and the extraction job picks it up on its next run.
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE posts SET content=?, transcript_status='done', "
            "transcript_source=? WHERE id=?",
            (content, source, post_id),
        )


def mark_extracted(post_id: int, version: str) -> None:
    """Mark a post done and stamp the prompt version it was extracted with."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE posts SET extraction_status='done', extraction_version=? WHERE id=?",
            (version, post_id),
        )


def list_recent_posts(limit: int = 50) -> list[dict]:
    """A single merged timeline across all enabled accounts (newest first),
    each post carrying its author (person_key / display_name / avatar). Trades
    are attached by the route via ``list_trades_for_posts``."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT p.id, p.platform, p.platform_post_id, p.url, p.content, "
            "       p.posted_at, p.extraction_status, p.title, "
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
            "       p.posted_at, p.extraction_status, p.title "
            "FROM posts p "
            "JOIN tracked_accounts t ON t.id = p.account_id "
            "WHERE t.person_key=? "
            "ORDER BY p.posted_at DESC LIMIT ?",
            (person_key, limit),
        ).fetchall()
        return [dict(r) for r in rows]
