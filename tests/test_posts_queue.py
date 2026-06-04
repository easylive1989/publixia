"""Extraction queue: pending + error are retryable; done/skipped are terminal."""
from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo


def _make_post(ext_id: str):
    acc = accounts_repo.list_accounts()[0]
    pid, _ = posts_repo.upsert_post(
        acc["id"], "threads", ext_id, "u", "c", "2026-06-01T00:00:00"
    )
    return pid


def test_pending_and_error_are_queued_done_is_not():
    p_pending = _make_post("PEND")
    p_error = _make_post("ERR")
    p_done = _make_post("DONE")
    posts_repo.set_extraction_status(p_error, "error")
    posts_repo.set_extraction_status(p_done, "done")

    queued = {p["id"] for p in posts_repo.list_pending_posts(limit=50)}
    assert p_pending in queued
    assert p_error in queued        # error is retried
    assert p_done not in queued     # done is terminal
