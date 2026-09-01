"""Sync 台股每日「指數收盤 + 成交金額」into market_volume_daily.

TWSE FMTQIK 一次一個月，
  所以從「最新一列所在的月份」抓到當月；空表則自 ``BACKFILL_START`` 回補整段
  歷史（請求之間有停頓，TWSE 會擋太兇的呼叫端）。
抓不到列就往上拋，讓 scheduler 記 error 並推 🚨。
"""
import logging
import time
from datetime import date

from core.markets import TW
from core.twse import fetch_month, month_range
from repositories import market_volume as repo

logger = logging.getLogger(__name__)

# 冷熱判讀的參考 sheet 從 2016 起算；近一年百分位需要 ~1 年暖身，回補到
# 2016 讓迴歸有足夠的位階跨度（8千點 → 4萬點）。
BACKFILL_START = date(2016, 1, 1)
_PAUSE_SECONDS = 2.0

def run_market_volume_sync(today: date | None = None) -> dict:
    """TW scheduler entry point. Returns {"months": …, "rows": …}."""
    today = today or date.today()
    latest = repo.latest_date(TW)
    start = date.fromisoformat(latest) if latest else BACKFILL_START

    months = month_range(start, today)
    total = 0
    for i, (y, m) in enumerate(months):
        if i:  # pause between month requests, not before the first/only one
            time.sleep(_PAUSE_SECONDS)
        total += repo.upsert_days(TW, fetch_month(y, m))
    logger.info("market_volume_synced months=%d rows=%d", len(months), total)
    return {"months": len(months), "rows": total}
