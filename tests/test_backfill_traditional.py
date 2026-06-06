"""Backfill: stored Simplified podcast transcripts → Traditional + re-queue."""
from db.connection import get_connection
from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo
from services.backfill_traditional import backfill_podcast_traditional


def _acc():
    return accounts_repo.list_accounts()[0]["id"]


def _row(pid):
    with get_connection() as c:
        return dict(c.execute(
            "SELECT content, extraction_status FROM posts WHERE id=?", (pid,)
        ).fetchone())


def test_converts_simplified_and_requeues_extraction():
    pid, _ = posts_repo.upsert_post(
        _acc(), "podcast", "EP1", "u", "", "2026-06-01T00:00:00",
        audio_url="https://cdn/ep1.mp3")
    posts_repo.set_post_transcript(pid, "欢迎收听股癌,本集由软件赞助", "groq")
    posts_repo.mark_extracted(pid, "v5")  # was already extracted

    res = backfill_podcast_traditional()

    assert res["converted"] == 1
    row = _row(pid)
    assert row["content"] == "歡迎收聽股癌,本集由軟體贊助"
    assert row["extraction_status"] == "pending"  # re-queued on Traditional content


def test_idempotent_leaves_traditional_untouched():
    pid, _ = posts_repo.upsert_post(
        _acc(), "podcast", "EP2", "u", "", "2026-06-01T00:00:00",
        audio_url="https://cdn/ep2.mp3")
    posts_repo.set_post_transcript(pid, "歡迎收聽繁體內容", "rss")
    posts_repo.mark_extracted(pid, "v5")

    res = backfill_podcast_traditional()

    assert res["converted"] == 0
    assert _row(pid)["extraction_status"] == "done"  # not re-queued


def test_skips_threads_and_empty():
    p_thread, _ = posts_repo.upsert_post(_acc(), "threads", "T1", "u", "买进台积电", "2026-06-01T00:00:00")
    p_empty, _ = posts_repo.upsert_post(
        _acc(), "podcast", "EP3", "u", "", "2026-06-01T00:00:00", audio_url="https://cdn/ep3.mp3")

    res = backfill_podcast_traditional()

    assert res["converted"] == 0  # threads not scanned; empty podcast skipped
    assert _row(p_thread)["content"] == "买进台积电"  # threads untouched
