"""Drain the pending-post queue: extract trades → normalize → persist → notify.

Scheduler entry point ``run_extraction`` runs shortly after each scrape. For
every newly-extracted post that yields ≥1 trade it fires a Discord
notification (only here, on the pending→done transition, so re-runs don't
re-notify).
"""
import logging

from core.discord import send_to_discord
from core.settings import settings
from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo
from repositories import trades as trades_repo
from services.normalization import normalize
from services.price_tracking_runner import run_price_tracking
from services.trade_extraction import PROMPT_VERSION, extract_trades

logger = logging.getLogger(__name__)

_DIRECTION_LABEL = {
    "buy": "🟢 買進",
    "sell": "🔴 賣出",
    "hold": "🟡 續抱",
    "bullish": "📈 看多",
    "bearish": "📉 看空",
}


def _format_trade(t: dict) -> str:
    symbol = t.get("ticker") or t["raw_symbol"]
    label = _DIRECTION_LABEL.get(t["direction"], t["direction"])
    extra = []
    if t.get("price"):
        extra.append(f"@{t['price']}")
    if t.get("quantity"):
        extra.append(f"{t['quantity']} 張")
    suffix = (" " + " ".join(extra)) if extra else ""
    return f"{label} {symbol}{suffix}"


def _notify(display_name: str, url: str, trades: list[dict]) -> None:
    webhook = settings.discord_copytrade_webhook_url
    if not webhook:
        return
    lines = "\n".join(_format_trade(t) for t in trades)
    content = f"**{display_name}** 偵測到新交易訊號\n{lines}\n{url}"
    try:
        send_to_discord(webhook.get_secret_value(), {"content": content})
    except Exception:  # noqa: BLE001 — notification failure must not block extraction
        logger.exception("discord_notify_failed url=%s", url)


def run_extraction(limit: int = 20) -> dict:
    """Process pending posts only.

    Stale re-extraction (reprocessing every ``done`` post when ``PROMPT_VERSION``
    bumps) is intentionally NOT done here: it would overwrite manual corrections
    to ``extracted_trades`` (see the fix-trade-signal skill). A prompt upgrade
    therefore only affects new/pending posts. To deliberately reprocess old posts
    after a prompt change, re-queue them (``set_extraction_status(id, 'pending')``)
    — ``list_stale_extraction_posts`` is kept for that manual path.
    """
    posts = posts_repo.list_pending_posts(limit=limit)

    processed = 0
    with_trades = 0
    errors = 0

    for post in posts:
        # whether the post already had trades — gates Discord so re-extraction
        # of an existing post doesn't re-notify.
        had_trades = trades_repo.has_existing_trades(post["id"])
        try:
            raw_trades = extract_trades(post["content"])
        except Exception:  # noqa: BLE001 — mark error, keep going
            logger.exception("extraction_failed post_id=%s", post["id"])
            posts_repo.set_extraction_status(post["id"], "error")
            errors += 1
            continue

        for t in raw_trades:
            ticker, market = normalize(t["raw_symbol"])
            t["ticker"] = ticker
            t["market"] = market

        trades_repo.save_trades(
            post["id"], raw_trades, model=settings.cf_ai_model, prompt_version=PROMPT_VERSION
        )
        posts_repo.mark_extracted(post["id"], PROMPT_VERSION)
        processed += 1

        if raw_trades:
            with_trades += 1
            if not had_trades:  # only notify the first time a post yields trades
                account = accounts_repo.get_account(post["account_id"])
                display_name = account["display_name"] if account else "追蹤帳號"
                _notify(display_name, post.get("url", ""), raw_trades)

    summary = {
        "processed": processed,
        "with_trades": with_trades,
        "errors": errors,
    }
    logger.info("run_extraction_done %s", summary)

    # 新解析出的個股馬上算一輪價格，「最新」不必等下一個 price_tracking tick。
    # 包 try/except：yfinance 出包不應該擋住 extraction 本身。
    try:
        run_price_tracking()
    except Exception:  # noqa: BLE001
        logger.exception("price_tracking_after_extraction_failed")

    return summary
