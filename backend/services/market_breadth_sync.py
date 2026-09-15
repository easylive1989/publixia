"""逐交易日同步 TWSE MI_INDEX 的上市股票漲跌家數。

最近缺資料的交易日優先，每次補一季約 66 日；每次排程亦重抓最新交易日，讓
證交所若修訂收盤統計時能覆蓋舊值。
"""
import logging
import time
from datetime import date, datetime

import pytz

from core.errors import FetcherError
from core.markets import TW
from core.twse_breadth import fetch_day
from repositories import market_breadth as repo
from repositories import market_volume

logger = logging.getLogger(__name__)

BATCH_SIZE = 66
_PAUSE_SECONDS = 5.0
_RETRY_DELAYS = (15.0, 30.0, 60.0)
TST = pytz.timezone("Asia/Taipei")


def _fetch_with_retry(iso: str) -> dict:
    day = date.fromisoformat(iso)
    attempts = len(_RETRY_DELAYS) + 1
    for attempt in range(attempts):
        try:
            row = fetch_day(day)
            if row is None:
                raise FetcherError(f"TWSE MI_INDEX 對交易日 {iso} 回覆無資料")
            return row
        except FetcherError as exc:
            if attempt == len(_RETRY_DELAYS):
                raise
            delay = _RETRY_DELAYS[attempt]
            logger.warning(
                "market_breadth_retry day=%s attempt=%d/%d delay=%.1f error=%s",
                iso, attempt + 1, attempts, delay, exc,
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


def run_market_breadth_sync(
    today: date | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict:
    today = today or datetime.now(TST).date()
    market_dates = [
        row["date"] for row in market_volume.list_days(TW)
        if row["date"] <= today.isoformat()
    ]
    if not market_dates:
        raise FetcherError("MI_INDEX sync 找不到 market_volume_daily 交易日")

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
            logger.error("market_breadth_day_failed day=%s error=%s", iso, exc)
            continue
        written += repo.upsert_days(TW, [row])
        if iso in missing:
            completed_missing.add(iso)

    remaining = max(0, len(missing) - len(completed_missing))
    logger.info(
        "market_breadth_synced requested=%d rows=%d failed=%d remaining=%d",
        len(targets), written, len(failures), remaining,
    )
    if failures:
        details = "; ".join(f"{day}: {error}" for day, error in failures[:5])
        if len(failures) > 5:
            details += f"; 另有 {len(failures) - 5} 日"
        raise FetcherError(
            "MI_INDEX sync 部分失敗 "
            f"requested={len(targets)} rows={written} failed={len(failures)} "
            f"remaining={remaining}: {details}"
        )
    return {"requested": len(targets), "rows": written, "remaining": remaining}
