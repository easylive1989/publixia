"""Alert routes: list, create, delete, toggle."""
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_token, require_user
from api.schemas.alerts import AlertRequest, AlertToggleRequest
from repositories.alerts import (
    add_alert, delete_alert, list_alerts, set_alert_enabled,
)
from services.alert_registry import get_indicator
from services import indicators  # noqa: F401  ← trigger auto-register
from fetchers.fundamentals_stock import to_finmind_id as fundamentals_to_finmind_id

router = APIRouter(prefix="/api", tags=["alerts"], dependencies=[Depends(require_token)])


VALID_TARGET_TYPES = {"indicator", "stock", "stock_indicator"}
VALID_CONDITIONS = {
    "above", "below",
    "streak_above", "streak_below",
    "percentile_above", "percentile_below",
    "yoy_above", "yoy_below",
}


@router.get("/alerts")
def get_alerts(user: dict = Depends(require_user)):
    return list_alerts(user["id"])


@router.post("/alerts")
def create_alert(req: AlertRequest, user: dict = Depends(require_user)):
    if req.target_type not in VALID_TARGET_TYPES:
        raise HTTPException(status_code=400, detail="Invalid target_type")
    if req.condition not in VALID_CONDITIONS:
        raise HTTPException(status_code=400, detail="Invalid condition")

    is_streak = req.condition.startswith("streak_")
    if is_streak:
        if req.window_n is None:
            raise HTTPException(status_code=400, detail="streak condition requires window_n")
        if req.window_n < 2 or req.window_n > 30:
            raise HTTPException(status_code=400, detail="window_n must be 2..30")

    is_percentile = req.condition.startswith("percentile_")
    if is_percentile and (req.threshold < 0 or req.threshold > 100):
        raise HTTPException(status_code=400, detail="percentile threshold must be 0..100")

    if req.target_type == "indicator":
        spec = get_indicator("indicator", req.target)
        if spec is None:
            raise HTTPException(status_code=400, detail="Unknown indicator")
        if not spec.supports(req.condition):
            raise HTTPException(
                status_code=400,
                detail=f"indicator {req.target} does not support {req.condition}",
            )
        target = req.target
    elif req.target_type == "stock_indicator":
        if not req.indicator_key:
            raise HTTPException(status_code=400, detail="stock_indicator requires indicator_key")
        spec = get_indicator("stock_indicator", req.indicator_key)
        if spec is None:
            raise HTTPException(status_code=400, detail="Unknown indicator_key")
        if fundamentals_to_finmind_id(req.target) is None:
            raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) supported")
        if not spec.supports(req.condition):
            raise HTTPException(
                status_code=400,
                detail=f"indicator {req.indicator_key} does not support condition {req.condition}",
            )
        target = req.target.upper()
    else:  # stock
        target = req.target.upper()

    alert_id = add_alert(user["id"], req.target_type, target, req.condition,
                         req.threshold,
                         indicator_key=req.indicator_key, window_n=req.window_n)
    return {"id": alert_id}


@router.delete("/alerts/{alert_id}")
def remove_alert(alert_id: int, user: dict = Depends(require_user)):
    delete_alert(user["id"], alert_id)
    return {"ok": True}


@router.patch("/alerts/{alert_id}")
def toggle_alert(alert_id: int, req: AlertToggleRequest,
                 user: dict = Depends(require_user)):
    set_alert_enabled(user["id"], alert_id, req.enabled)
    return {"ok": True}
