"""Scraper orchestration — the scheduler entry points.

``scrape_all_enabled`` is wired into the scheduler; it walks every enabled
tracked account, scrapes recent posts, and upserts them. New posts land with
``extraction_status='pending'`` for the extraction job to pick up.
"""
import logging

from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo
from scrapers.threads import ThreadsScraper

logger = logging.getLogger(__name__)

_SCRAPERS = {
    "threads": ThreadsScraper(),
}


def scrape_account(account: dict) -> int:
    """Scrape one account and upsert its posts. Returns count of NEW posts."""
    scraper = _SCRAPERS.get(account["platform"])
    if scraper is None:
        logger.warning(
            "no_scraper_for_platform platform=%s handle=%s",
            account["platform"], account.get("handle"),
        )
        return 0

    known_ids = posts_repo.known_post_ids(account["id"])
    scraped = scraper.fetch_recent(
        account, account.get("backfill_months", 3), known_ids=known_ids
    )
    new_count = 0
    for post in scraped:
        _, is_new = posts_repo.upsert_post(
            account_id=account["id"],
            platform=account["platform"],
            platform_post_id=post.platform_post_id,
            url=post.url,
            content=post.content,
            posted_at=post.posted_at,
        )
        if is_new:
            new_count += 1
    logger.info(
        "scrape_account_done handle=%s scraped=%d new=%d",
        account.get("handle"), len(scraped), new_count,
    )
    return new_count


def scrape_all_enabled() -> dict:
    """Scrape every enabled account. Returns per-account new-post counts."""
    summary: dict[str, int] = {}
    for account in accounts_repo.list_accounts(enabled_only=True):
        try:
            summary[account["handle"]] = scrape_account(account)
        except Exception:  # noqa: BLE001 — one bad account shouldn't kill the run
            logger.exception("scrape_account_failed handle=%s", account.get("handle"))
            summary[account["handle"]] = -1
    logger.info("scrape_all_done summary=%s", summary)
    return summary
