"""大盤 API。

- ``GET /api/market/volume-heat``          大盤成交金額冷熱判讀（最新 + 近 N 日；
  省略 ``days`` 回傳全歷史）
- ``POST /api/market/volume-heat/refresh`` 手動觸發 TWSE 同步（背景執行；首次
  部署時用來立即回補歷史，不用等每日排程）
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException

from services.market_heat import get_market_heat

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/volume-heat")
def volume_heat(days: int | None = None):
    if days is not None and not (1 <= days <= 4000):
        raise HTTPException(status_code=400, detail="days 超出範圍")
    return get_market_heat(days=days)


@router.post("/volume-heat/refresh")
def refresh_volume_heat(background_tasks: BackgroundTasks):
    from services.market_volume_sync import run_market_volume_sync

    background_tasks.add_task(run_market_volume_sync)
    return {"status": "scheduled"}
