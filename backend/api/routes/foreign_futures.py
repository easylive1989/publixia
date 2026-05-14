"""GET /api/futures/tw/foreign-flow — TX K-line + foreign-investor metrics.

Delegates payload composition to ``services.foreign_flow_payload`` so the
same shape can be reused by the markdown / AI-report pipeline without
the route owning the assembly logic.

Also exposes POST /api/futures/tw/foreign-flow/refresh to trigger the
five scheduled fetchers that feed this page on demand.
"""
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_foreign_futures_permission
from fetchers.futures import fetch_tw_futures
from fetchers.institutional_futures import fetch_latest as fetch_inst_futures
from fetchers.institutional_options import fetch_latest as fetch_inst_options
from fetchers.large_trader import fetch_latest as fetch_large_trader
from fetchers.txo_strike_oi import fetch_latest as fetch_txo_strike_oi
from services.foreign_flow_payload import assemble_foreign_flow_payload

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["futures"],
    dependencies=[Depends(require_foreign_futures_permission)],
)


@router.get("/futures/tw/foreign-flow")
def tw_futures_foreign_flow(time_range: str = "6M"):
    try:
        payload = assemble_foreign_flow_payload(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown time_range")
    if payload is None:
        raise HTTPException(status_code=404, detail="No TX history available")
    return payload


# Fetchers feeding this page. Run sequentially so each TAIFEX request
# respects the per-fetcher 2-second throttle without crossing fetchers.
# Order matters: K-line first so closes exist when metrics resolve.
_REFRESH_FETCHERS: list[tuple[str, callable]] = [
    ("tw_futures",    fetch_tw_futures),
    ("inst_futures",  fetch_inst_futures),
    ("inst_options",  fetch_inst_options),
    ("large_trader",  fetch_large_trader),
    ("txo_strike_oi", fetch_txo_strike_oi),
]

# Guard against concurrent manual refreshes; running 5 TAIFEX fetchers
# in parallel would burn through rate limits and confuse the user.
_refresh_lock = threading.Lock()


@router.post("/futures/tw/foreign-flow/refresh")
def tw_futures_foreign_flow_refresh():
    """Trigger every fetcher that feeds the 外資動向 page on demand.

    Sequential, upsert-based. Returns a per-fetcher status map so the
    frontend can surface partial failures without blocking the whole
    page refresh.
    """
    if not _refresh_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="A refresh is already in progress",
        )
    try:
        results: dict[str, dict[str, str | None]] = {}
        for name, fn in _REFRESH_FETCHERS:
            try:
                fn()
            except Exception as e:
                logger.exception("foreign_flow_refresh_failed name=%s", name)
                results[name] = {"status": "error", "detail": str(e)[:200]}
            else:
                results[name] = {"status": "ok", "detail": None}
        ok_all = all(r["status"] == "ok" for r in results.values())
        return {"ok": ok_all, "results": results}
    finally:
        _refresh_lock.release()
