"""Indicator routes: dashboard, history, refresh."""
import json
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api._constants import INDICATOR_JOB_MAP, INDICATOR_NAMES, RANGE_DELTAS
from api.dependencies import require_token
from repositories.indicators import (
    get_indicator_history, get_latest_indicator,
)
from services.scheduler_info import next_run_at
from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_all_stocks
from fetchers.fear_greed import fetch_fear_greed
from fetchers.chip_total import fetch_chip_total
from fetchers.ndc import fetch_ndc
from fetchers.volume import fetch_tw_volume, fetch_us_volume
from fetchers.futures import fetch_tw_futures

router = APIRouter(prefix="/api", tags=["indicators"], dependencies=[Depends(require_token)])


FETCHERS: dict[str, Callable] = {
    "taiex":      fetch_taiex,
    "fx":         fetch_fx,
    "fear_greed": fetch_fear_greed,
    "chip_total": fetch_chip_total,
    "ndc":        fetch_ndc,
    "stocks":     fetch_all_stocks,
    "tw_volume":  fetch_tw_volume,
    "us_volume":  fetch_us_volume,
    "tw_futures": fetch_tw_futures,
}


@router.get("/dashboard")
def dashboard():
    # Cache job → next_run_at lookups across the loop so chip_total fans
    # out to its six indicators with a single CronTrigger evaluation.
    next_run_cache: dict[str, str | None] = {}

    def _next_for(indicator: str) -> str | None:
        job = INDICATOR_JOB_MAP.get(indicator)
        if job is None:
            return None
        if job not in next_run_cache:
            dt = next_run_at(job)
            next_run_cache[job] = dt.isoformat() if dt else None
        return next_run_cache[job]

    result = {}
    for name in INDICATOR_NAMES:
        row = get_latest_indicator(name)
        if row:
            result[name] = {
                "value":          row["value"],
                "timestamp":      row["timestamp"],
                "extra":          json.loads(row["extra_json"]) if row["extra_json"] else {},
                "next_update_at": _next_for(name),
            }
    return result


@router.get("/history/{indicator}")
def history(indicator: str, time_range: str = "3M"):
    if indicator not in INDICATOR_NAMES:
        raise HTTPException(status_code=404, detail="Unknown indicator")
    delta = RANGE_DELTAS.get(time_range, RANGE_DELTAS["3M"])
    since = datetime.now(timezone.utc).replace(tzinfo=None) - delta
    rows = get_indicator_history(indicator, since)
    return [{"timestamp": r["timestamp"], "value": r["value"]} for r in rows]


@router.post("/refresh/{indicator}")
def refresh(indicator: str):
    fn = FETCHERS.get(indicator)
    if fn is None:
        raise HTTPException(status_code=404, detail="Unknown indicator")
    try:
        fn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}


@router.get("/indicators/spec")
def indicators_spec():
    """Return alert-able indicator specs grouped by target_type.

    Frontend (Phase 5) uses this to render the alert creation form.
    """
    from services.alert_registry import all_indicators
    from services import indicators as _indicators_pkg  # noqa: F401  ← trigger auto-register

    def _to_dict(spec):
        return {
            "key": spec.key,
            "label": spec.label,
            "unit": spec.unit,
            "supported_conditions": sorted(spec.supported_conditions),
        }

    bundle = all_indicators()
    return {
        "indicator":       [_to_dict(s) for s in bundle["indicator"]],
        "stock_indicator": [_to_dict(s) for s in bundle["stock_indicator"]],
    }
