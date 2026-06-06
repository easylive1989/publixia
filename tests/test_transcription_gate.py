"""The transcript_status gate: podcast posts are extracted only after transcription.

A podcast post sits in the transcription queue and is withheld from the extraction
queue until ``set_post_transcript`` marks it done; a text post is extractable at once.
"""
from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo


def _acc():
    return accounts_repo.list_accounts()[0]["id"]


def test_podcast_post_gated_until_transcribed():
    pid, _ = posts_repo.upsert_post(
        _acc(), "podcast", "EP1", "u", "", "2026-06-01T00:00:00",
        audio_url="https://cdn/ep1.mp3",
    )

    # Before transcription: in the transcription queue, NOT in the extraction queue.
    assert pid in {p["id"] for p in posts_repo.list_pending_transcription_posts(limit=50)}
    assert pid not in {p["id"] for p in posts_repo.list_pending_posts(limit=50)}

    # Transcribe it.
    posts_repo.set_post_transcript(pid, "逐字稿內容", "groq")

    # After transcription: out of the transcription queue, now in the extraction queue.
    assert pid not in {p["id"] for p in posts_repo.list_pending_transcription_posts(limit=50)}
    assert pid in {p["id"] for p in posts_repo.list_pending_posts(limit=50)}


def test_text_post_is_extractable_immediately():
    pid, _ = posts_repo.upsert_post(
        _acc(), "threads", "T1", "u", "hello", "2026-06-01T00:00:00"
    )
    assert pid in {p["id"] for p in posts_repo.list_pending_posts(limit=50)}
    assert pid not in {p["id"] for p in posts_repo.list_pending_transcription_posts(limit=50)}


def test_transcription_queue_is_newest_first():
    acc = accounts_repo.list_accounts()[0]["id"]
    older, _ = posts_repo.upsert_post(
        acc, "podcast", "OLD", "u", "", "2026-05-01T00:00:00", audio_url="https://cdn/old.mp3")
    newer, _ = posts_repo.upsert_post(
        acc, "podcast", "NEW", "u", "", "2026-06-01T00:00:00", audio_url="https://cdn/new.mp3")
    queue = [p["id"] for p in posts_repo.list_pending_transcription_posts(limit=10)]
    assert queue.index(newer) < queue.index(older)  # newest transcribed first


def test_transcription_error_is_retried():
    pid, _ = posts_repo.upsert_post(
        _acc(), "podcast", "EP2", "u", "", "2026-06-01T00:00:00",
        audio_url="https://cdn/ep2.mp3",
    )
    posts_repo.set_transcript_status(pid, "error")
    assert pid in {p["id"] for p in posts_repo.list_pending_transcription_posts(limit=50)}
    # still gated out of extraction while transcript not done
    assert pid not in {p["id"] for p in posts_repo.list_pending_posts(limit=50)}
