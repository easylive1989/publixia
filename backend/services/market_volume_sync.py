"""Sync 各市場的每日「指數收盤 + 量能」into market_volume_daily.

兩個市場、兩支 job，因為資料源的取法完全不同：

- **TW**（`market_volume_sync`，收盤後 16:00 TST）—— TWSE FMTQIK 一次一個月，
  所以從「最新一列所在的月份」抓到當月；空表則自 ``BACKFILL_START`` 回補整段
  歷史（請求之間有停頓，TWSE 會擋太兇的呼叫端）。
- **US**（`nasdaq_volume_sync`，美股收盤後）—— Yahoo 的 chart endpoint 一個請求
  就能拿整段區間，所以不管回補還是每日增量都只發一次請求。

兩支都不靜默：抓不到列就往上拋，讓 scheduler 記 error 並推 🚨。
"""
import logging
import time
from datetime import date, datetime, timedelta, timezone

from core.errors import FetcherParseError
from core.markets import TW, US
from core.nasdaq import fetch_range
from core.twse import fetch_month, month_range
from repositories import market_volume as repo

logger = logging.getLogger(__name__)

# 冷熱判讀的參考 sheet 從 2016 起算；近一年百分位需要 ~1 年暖身，回補到
# 2016 讓迴歸有足夠的位階跨度（8千點 → 4萬點）。美股用同一個起點，兩邊的
# 「近一年百分位」才有可比的歷史深度。
BACKFILL_START = date(2016, 1, 1)
_PAUSE_SECONDS = 2.0

# 增量同步往回多抓幾天：Yahoo 對「盤還沒收完」的當天會給一根量能不完整的
# daily bar，隔天再抓一次就會被正確值覆蓋（upsert on (market, date)）。
# 也順便吃掉資料源事後修正。至少 10 天是 core.nasdaq.fetch_range 的前提 ——
# 它拿「區間內一個交易日都沒有」當故障。
_US_OVERLAP_DAYS = 10


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


def run_nasdaq_volume_sync(today: date | None = None) -> dict:
    """US scheduler entry point. Returns {"start": …, "rows": …}.

    ``today`` 用美東日期算：job 在 TST 清晨跑，那時美東還是前一天，用台北日期
    當區間終點會多要一天（無妨），用 UTC 則剛好落在美股收盤與換日之間。這裡
    取 UTC date 已經足夠涵蓋 —— period2 本來就再往後推一天。
    """
    today = today or datetime.now(timezone.utc).date()
    latest = repo.latest_date(US)
    start = (
        date.fromisoformat(latest) - timedelta(days=_US_OVERLAP_DAYS)
        if latest
        else BACKFILL_START
    )

    rows = fetch_range(start, today)
    written = repo.upsert_days(US, rows)
    if not written:
        raise FetcherParseError(
            f"Nasdaq 同步 {start}~{today} 一列都沒寫入 —— fetch_range 回了 "
            f"{len(rows)} 列，檢查 core/nasdaq.py 的解析"
        )
    logger.info(
        "nasdaq_volume_synced start=%s end=%s rows=%d latest=%s",
        start, today, written, rows[-1]["date"],
    )
    return {"start": start.isoformat(), "rows": written, "latest": rows[-1]["date"]}
