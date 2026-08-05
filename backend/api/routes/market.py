"""大盤 API。

- ``GET /api/market/volume-heat``          成交量冷熱判讀（最新 + 近 N 日；
  省略 ``days`` 回傳全歷史）
- ``POST /api/market/volume-heat/refresh`` 手動觸發同步（背景執行；首次部署時
  用來立即回補歷史，不用等每日排程）

兩支都吃 ``market``：``TW``（台股加權 + 成交金額）或 ``US``（Nasdaq Composite
+ 成交股數）。省略時是 ``TW``。
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException

from core.markets import MARKETS, TW, US
from services.market_heat import get_market_heat

router = APIRouter(prefix="/api/market", tags=["market"])


def _check_market(market: str) -> str:
    if market not in MARKETS:
        raise HTTPException(
            status_code=400,
            detail=f"market 只能是 {'/'.join(MARKETS)}",
        )
    return market


@router.get("/volume-heat")
def volume_heat(days: int | None = None, market: str = TW):
    if days is not None and not (1 <= days <= 4000):
        raise HTTPException(status_code=400, detail="days 超出範圍")
    return get_market_heat(days=days, market=_check_market(market))


@router.post("/volume-heat/refresh")
def refresh_volume_heat(background_tasks: BackgroundTasks, market: str = TW):
    from services import market_volume_sync

    runner = {
        TW: market_volume_sync.run_market_volume_sync,
        US: market_volume_sync.run_nasdaq_volume_sync,
    }[_check_market(market)]
    background_tasks.add_task(runner)
    return {"status": "scheduled", "market": market}
