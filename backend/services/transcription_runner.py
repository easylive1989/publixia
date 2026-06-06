"""Drain the pending-transcription queue: fetch/transcribe → store transcript.

Scheduler entry point ``run_transcription`` runs between scrape and extract.
For each podcast post awaiting a transcript it produces text (RSS transcript or
Groq Whisper) and stores it as the post's content, which flips the transcript
gate open so the extraction job picks the post up on its next tick. It does NOT
call extraction itself — keeping the stages decoupled, like scrape→extract.
"""
import logging

from repositories import posts as posts_repo
from services.transcription import transcribe_post

logger = logging.getLogger(__name__)


def run_transcription(limit: int = 5) -> dict:
    """Transcribe pending podcast posts. ``limit`` is low because each item is
    heavy (audio download + ffmpeg + Groq rate limits)."""
    pending = posts_repo.list_pending_transcription_posts(limit=limit)

    processed = 0
    errors = 0
    for post in pending:
        try:
            text, source = transcribe_post(
                post.get("audio_url"), post.get("transcript_url"),
                prompt=post.get("transcribe_prompt"),
            )
        except Exception:  # noqa: BLE001 — mark error (retryable), keep going
            logger.exception("transcription_failed post_id=%s", post["id"])
            posts_repo.set_transcript_status(post["id"], "error")
            errors += 1
            continue
        posts_repo.set_post_transcript(post["id"], text, source)
        processed += 1

    summary = {"processed": processed, "errors": errors}
    logger.info("run_transcription_done %s", summary)
    return summary
