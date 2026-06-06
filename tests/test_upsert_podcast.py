"""upsert_post podcast handling: transcript_status gate seeding + content protection.

- A podcast insert (audio_url present) seeds transcript_status='pending' and stores
  audio_url/transcript_url/title.
- A text-platform insert (threads) leaves transcript_status NULL so extraction runs
  immediately (unchanged behaviour).
- Re-upserting a podcast post with an empty content placeholder must NOT wipe an
  already-stored transcript nor reset transcript_status (re-scrape shouldn't re-transcribe).
"""
from db.connection import get_connection
from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo


def _acc():
    return accounts_repo.list_accounts()[0]["id"]


def _row(post_id: int) -> dict:
    with get_connection() as conn:
        return dict(conn.execute(
            "SELECT content, audio_url, transcript_url, transcript_status, title "
            "FROM posts WHERE id=?",
            (post_id,),
        ).fetchone())


def test_podcast_insert_seeds_pending_and_stores_fields():
    pid, is_new = posts_repo.upsert_post(
        _acc(), "podcast", "EP1", "https://show/ep1", "",
        "2026-06-01T00:00:00",
        audio_url="https://cdn/ep1.mp3",
        transcript_url="https://cdn/ep1.vtt",
        title="第一集：台積電",
    )
    assert is_new
    row = _row(pid)
    assert row["transcript_status"] == "pending"
    assert row["audio_url"] == "https://cdn/ep1.mp3"
    assert row["transcript_url"] == "https://cdn/ep1.vtt"
    assert row["title"] == "第一集：台積電"


def test_threads_insert_leaves_transcript_status_null():
    pid, _ = posts_repo.upsert_post(
        _acc(), "threads", "T1", "u", "hello", "2026-06-01T00:00:00"
    )
    assert _row(pid)["transcript_status"] is None


def test_rescrape_does_not_wipe_transcript_or_reset_status():
    pid, _ = posts_repo.upsert_post(
        _acc(), "podcast", "EP2", "https://show/ep2", "",
        "2026-06-01T00:00:00", audio_url="https://cdn/ep2.mp3",
    )
    # Simulate transcription filling the content and marking it done.
    with get_connection() as conn:
        conn.execute(
            "UPDATE posts SET content=?, transcript_status='done' WHERE id=?",
            ("完整逐字稿…", pid),
        )
    assert _row(pid)["transcript_status"] == "done"

    # A later scrape re-sees the same episode with an empty content placeholder.
    posts_repo.upsert_post(
        _acc(), "podcast", "EP2", "https://show/ep2", "",
        "2026-06-01T00:00:00", audio_url="https://cdn/ep2.mp3",
    )
    row = _row(pid)
    assert row["content"] == "完整逐字稿…"      # transcript preserved
    assert row["transcript_status"] == "done"   # not re-queued for transcription


def test_rescrape_updates_title_and_url():
    pid, _ = posts_repo.upsert_post(
        _acc(), "podcast", "EP3", "https://show/ep3", "",
        "2026-06-01T00:00:00", audio_url="https://cdn/ep3.mp3", title="舊標題",
    )
    posts_repo.upsert_post(
        _acc(), "podcast", "EP3", "https://show/ep3-new", "",
        "2026-06-01T00:00:00", audio_url="https://cdn/ep3.mp3", title="新標題",
    )
    row = _row(pid)
    assert row["title"] == "新標題"
