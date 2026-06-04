"""Daily job: compute 7d/1m price windows for mentioned stocks.

Recomputes rows whose window hasn't finished yet (status != done), so a
recent post's 7d/1m fill in once enough calendar time has elapsed.
"""
import logging
from datetime import datetime

from repositories import price_tracking as repo
from services.price_history import compute_window

logger = logging.getLogger(__name__)


def run_price_tracking(limit: int | None = None) -> dict:
    targets = repo.list_tracking_targets()
    if limit:
        targets = targets[:limit]

    updated = 0
    errors = 0
    for t in targets:
        try:
            post_dt = datetime.fromisoformat(t["posted_at"])
            window = compute_window(t["ticker"], t["market"], post_dt)
            repo.upsert_tracking(t["post_id"], t["ticker"], t["market"], window)
            updated += 1
        except Exception:  # noqa: BLE001 — one ticker shouldn't kill the run
            logger.exception(
                "price_tracking_failed post=%s ticker=%s", t["post_id"], t["ticker"]
            )
            errors += 1

    logger.info("price_tracking_done updated=%d errors=%d", updated, errors)
    return {"updated": updated, "errors": errors}
