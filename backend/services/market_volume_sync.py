"""Sync TWSE 大盤成交統計 into market_volume_daily.

Run by the ``market_volume_sync`` scheduler job (daily after close). Fetches
month-by-month from the month of the latest stored row through the current
month — so the steady state is one request a day, and an empty table
backfills the whole history since ``BACKFILL_START`` on first run (with a
polite pause between requests; TWSE rate-limits aggressive callers).
"""
import logging
import time
from datetime import date

from core.twse import fetch_month, month_range
from repositories import market_volume as repo

logger = logging.getLogger(__name__)

# 冷熱判讀的參考 sheet 從 2016 起算；近一年百分位需要 ~1 年暖身，回補到
# 2016 讓迴歸有足夠的位階跨度（8千點 → 4萬點）。
BACKFILL_START = date(2016, 1, 1)
_PAUSE_SECONDS = 2.0


def run_market_volume_sync(today: date | None = None) -> dict:
    """Scheduler entry point. Returns {"months": …, "rows": …}."""
    today = today or date.today()
    latest = repo.latest_date()
    start = date.fromisoformat(latest) if latest else BACKFILL_START

    months = month_range(start, today)
    total = 0
    for i, (y, m) in enumerate(months):
        if i:  # pause between month requests, not before the first/only one
            time.sleep(_PAUSE_SECONDS)
        total += repo.upsert_days(fetch_month(y, m))
    logger.info("market_volume_synced months=%d rows=%d", len(months), total)
    return {"months": len(months), "rows": total}
