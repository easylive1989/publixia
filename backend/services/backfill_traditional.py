"""Convert already-stored podcast transcripts to Traditional Chinese.

Episodes transcribed before the OpenCC step was added are stored in Simplified.
This rewrites their ``content`` to Traditional and re-queues extraction (the
extraction prompt is Traditional, so a Traditional transcript may surface trades
the Simplified one missed). Idempotent: once a transcript is already Traditional
the conversion is a no-op, so the row is left untouched and not re-queued.
"""
import logging

from core.chinese import to_traditional
from db.connection import get_connection

logger = logging.getLogger(__name__)


def backfill_podcast_traditional() -> dict:
    """Rewrite Simplified podcast transcripts to Traditional, re-queueing each
    changed post for extraction. Returns ``{"scanned": N, "converted": M}``."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, content FROM posts WHERE platform='podcast' AND content != ''"
        ).fetchall()
        converted = 0
        for r in rows:
            trad = to_traditional(r["content"])
            if trad != r["content"]:
                conn.execute(
                    "UPDATE posts SET content=?, extraction_status='pending' WHERE id=?",
                    (trad, r["id"]),
                )
                converted += 1
    logger.info("backfill_traditional scanned=%d converted=%d", len(rows), converted)
    return {"scanned": len(rows), "converted": converted}
