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
# TWSE 會對同一 IP 的短時間連續請求限流。0.35 秒在正式 VPS 實測會先成功
# 1～2 日，之後整段逾時；5 秒讓 260 日批次約 22 分鐘，仍可在晚間排程完成。
_PAUSE_SECONDS = 5.0
_RETRY_DELAYS = (15.0, 30.0, 60.0)


def _fetch_with_retry(iso: str) -> dict:
    """抓一個交易日；暫時性失敗採退避重試，最後仍失敗才交給批次記錄。"""
    day = date.fromisoformat(iso)
    attempts = len(_RETRY_DELAYS) + 1
    for attempt in range(attempts):
        try:
            row = fetch_day(day)
            if row is None:
                raise FetcherError(f"TWSE BFI82U 對交易日 {iso} 回覆無資料")
            return row
        except FetcherError as exc:
            if attempt == len(_RETRY_DELAYS):
                raise
            delay = _RETRY_DELAYS[attempt]
            logger.warning(
                "institutional_flow_retry day=%s attempt=%d/%d delay=%.1f error=%s",
                iso, attempt + 1, attempts, delay, exc,
            )
            time.sleep(delay)

    raise AssertionError("unreachable")


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
    completed_missing: set[str] = set()
    failures: list[tuple[str, str]] = []
    for index, iso in enumerate(targets):
        if index:
            time.sleep(_PAUSE_SECONDS)
        try:
            row = _fetch_with_retry(iso)
        except FetcherError as exc:
            failures.append((iso, str(exc)))
            logger.error("institutional_flow_day_failed day=%s error=%s", iso, exc)
            continue
        # 每日即時落盤：長批次若中途遇到暫時性網路錯誤，已抓到的日期仍可保留，
        # 下次排程只需接續缺口，不會重做整批。
        written += repo.upsert_days(TW, [row])
        if iso in missing:
            completed_missing.add(iso)

    remaining = max(0, len(missing) - len(completed_missing))
    logger.info(
        "institutional_flow_synced requested=%d rows=%d failed=%d remaining=%d",
        len(targets), written, len(failures), remaining,
    )
    if failures:
        details = "; ".join(f"{day}: {error}" for day, error in failures[:5])
        if len(failures) > 5:
            details += f"; 另有 {len(failures) - 5} 日"
        raise FetcherError(
            "BFI82U sync 部分失敗 "
            f"requested={len(targets)} rows={written} failed={len(failures)} "
            f"remaining={remaining}: {details}"
        )
    return {"requested": len(targets), "rows": written, "remaining": remaining}


def run_institutional_flow_early_sync(today: date | None = None) -> dict:
    """16:10 第一版只刷新最新交易日，不在尖峰時段執行歷史回補。"""
    return run_institutional_flow_sync(today=today, batch_size=0)
