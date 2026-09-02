"""逐交易日同步 TWSE BFI82U 三大法人買賣金額。

BFI82U 一次只能查一天。首次部署從已有的 market_volume_daily 交易日中，由新到舊
每次補一批，讓最近一年先可用且不在單次排程猛打證交所；之後每日仍重抓最新交易
日，以便覆蓋較早時間取得的未定案版本。
"""
import logging
import time
from datetime import date

from core.errors import FetcherError
from core.markets import TW
from core.twse_institutional import fetch_day
from repositories import institutional_flow as repo
from repositories import market_volume

logger = logging.getLogger(__name__)

BATCH_SIZE = 260
_PAUSE_SECONDS = 0.35


def run_institutional_flow_sync(
    today: date | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """Scheduler entry point；最近缺資料的交易日優先，回傳同步進度。"""
    today = today or date.today()
    market_dates = [
        row["date"] for row in market_volume.list_days(TW)
        if row["date"] <= today.isoformat()
    ]
    if not market_dates:
        raise FetcherError("BFI82U sync 找不到 market_volume_daily 交易日")

    stored = repo.existing_dates(TW)
    missing = [day for day in reversed(market_dates) if day not in stored]
    targets = missing[:batch_size]
    latest = market_dates[-1]
    if latest not in targets:
        targets.insert(0, latest)

    written = 0
    for index, iso in enumerate(targets):
        if index:
            time.sleep(_PAUSE_SECONDS)
        row = fetch_day(date.fromisoformat(iso))
        if row is None:
            raise FetcherError(f"TWSE BFI82U 對交易日 {iso} 回覆無資料")
        # 每日即時落盤：長批次若中途遇到暫時性網路錯誤，已抓到的日期仍可保留，
        # 下次排程只需接續缺口，不會重做整批。
        written += repo.upsert_days(TW, [row])

    target_set = set(targets)
    remaining = max(0, len(missing) - sum(day in target_set for day in missing))
    logger.info(
        "institutional_flow_synced requested=%d rows=%d remaining=%d",
        len(targets), written, remaining,
    )
    return {"requested": len(targets), "rows": written, "remaining": remaining}
