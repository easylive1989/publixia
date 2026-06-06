"""Transcription runner: drains the queue, stores transcripts, marks errors,
and the scheduler job is registered with a valid cron."""
from apscheduler.triggers.cron import CronTrigger

import services.transcription_runner as runner
from jobs.registry import JOBS
from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo


def _podcast_post(ext_id: str):
    acc = accounts_repo.list_accounts()[0]["id"]
    pid, _ = posts_repo.upsert_post(
        acc, "podcast", ext_id, "u", "", "2026-06-01T00:00:00",
        audio_url=f"https://cdn/{ext_id}.mp3",
    )
    return pid


def _status(post_id: int) -> str:
    from db.connection import get_connection
    with get_connection() as conn:
        return conn.execute(
            "SELECT transcript_status FROM posts WHERE id=?", (post_id,)
        ).fetchone()[0]


def _content(post_id: int) -> str:
    from db.connection import get_connection
    with get_connection() as conn:
        return conn.execute(
            "SELECT content FROM posts WHERE id=?", (post_id,)
        ).fetchone()[0]


def test_successful_transcription_fills_content(monkeypatch):
    pid = _podcast_post("EP1")
    monkeypatch.setattr(runner, "transcribe_post", lambda a, t: ("逐字稿內容", "groq"))

    summary = runner.run_transcription(limit=10)

    assert summary == {"processed": 1, "errors": 0}
    assert _status(pid) == "done"
    assert _content(pid) == "逐字稿內容"


def test_failure_marks_error_and_continues(monkeypatch):
    p_ok = _podcast_post("OK")
    p_bad = _podcast_post("BAD")

    def fake(audio, transcript):
        if "BAD" in (audio or ""):
            raise RuntimeError("boom")
        return ("好的逐字稿", "rss")

    monkeypatch.setattr(runner, "transcribe_post", fake)
    summary = runner.run_transcription(limit=10)

    assert summary == {"processed": 1, "errors": 1}
    assert _status(p_ok) == "done"
    assert _status(p_bad) == "error"


def test_transcribe_podcasts_job_registered_with_valid_cron():
    spec = JOBS["transcribe_podcasts"]
    assert spec.fn is runner.run_transcription
    # must parse as a 5-field POSIX cron
    CronTrigger.from_crontab(spec.default_cron)
