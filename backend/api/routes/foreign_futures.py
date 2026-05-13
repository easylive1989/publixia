"""GET /api/futures/tw/foreign-flow — TX K-line + foreign-investor metrics.

Combines four data sources behind a single permission-gated endpoint:

1. TX daily OHLCV from `futures_daily` (existing fetcher)
2. Foreign-investor TX/MTX positions from `institutional_futures_daily`
3. Per-day blended metrics computed by `services.foreign_futures_metrics`
4. TX settlement dates from `futures_settlement_dates`

The frontend renders a 4-region synced chart from the assembled arrays.

Also exposes POST /api/futures/tw/foreign-flow/refresh to trigger the
five scheduled fetchers that feed this page on demand.
"""
import logging
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_foreign_futures_permission
from fetchers.futures import fetch_tw_futures
from fetchers.institutional_futures import fetch_latest as fetch_inst_futures
from fetchers.institutional_options import fetch_latest as fetch_inst_options
from fetchers.large_trader import fetch_latest as fetch_large_trader
from fetchers.txo_strike_oi import fetch_latest as fetch_txo_strike_oi
from repositories.futures import get_futures_daily_range
from repositories.indicators import get_indicator_history
from repositories.institutional_futures import (
    get_institutional_futures_range,
    get_settlement_dates_in_range,
)
from repositories.institutional_options import get_institutional_options_range
from repositories.txo_strike_oi import (
    get_latest_txo_strike_oi_date,
    get_txo_strike_oi_on_date,
)
from repositories.large_trader import get_large_trader_range
from services.foreign_futures_metrics import compute_metrics, compute_retail_ratio
from services.foreign_options_view import build_options_block
from services.strike_oi_view import build_strike_oi_block

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["futures"],
    dependencies=[Depends(require_foreign_futures_permission)],
)

RANGE_LOOKBACK_DAYS: dict[str, int] = {
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
    "3Y": 365 * 3,
}

# Pull a few extra days on the back side so the first visible day's
# net_change / realized_pnl can reference the day before the window.
_METRICS_WARMUP_DAYS = 14


@router.get("/futures/tw/foreign-flow")
def tw_futures_foreign_flow(time_range: str = "6M"):
    if time_range not in RANGE_LOOKBACK_DAYS:
        raise HTTPException(status_code=400, detail="Unknown time_range")

    today = datetime.now(timezone.utc).astimezone().date()
    days = RANGE_LOOKBACK_DAYS[time_range]
    window_start = today - timedelta(days=days)
    metrics_start = window_start - timedelta(days=_METRICS_WARMUP_DAYS)
    window_start_str  = window_start.strftime("%Y-%m-%d")
    metrics_start_str = metrics_start.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    # 1) K-line backbone
    tx_bars = get_futures_daily_range("TX", window_start_str)
    if not tx_bars:
        raise HTTPException(status_code=404, detail="No TX history available")
    tx_closes = {r["date"]: r["close"] for r in tx_bars if r.get("close") is not None}

    # 2) Institutional rows (with warm-up so net_change has a basis)
    tx_inst_rows  = get_institutional_futures_range("TX",  metrics_start_str)
    mtx_inst_rows = get_institutional_futures_range("MTX", metrics_start_str)

    # 3) Compute metrics across the union of inst dates
    metrics = compute_metrics(tx_inst_rows, mtx_inst_rows, tx_closes)
    metrics_by_date = {m["date"]: m for m in metrics}

    # 3b) Retail long/short ratio from TAIFEX 大額交易人 report
    lt_rows = get_large_trader_range(window_start_str)
    retail_ratio_by_date = compute_retail_ratio(lt_rows)

    # 3c) Foreign-investor spot net buy/sell (TWSE 整體外資現貨, 億元)
    spot_rows = get_indicator_history(
        "total_foreign_net",
        datetime.combine(window_start, datetime.min.time()),
    )
    spot_by_date = {r["date"]: r["value"] for r in spot_rows}

    # 4) Project metrics onto the K-line timeline.
    visible = [b for b in tx_bars if b["date"] >= window_start_str]
    dates: list[str] = []
    candles: list[dict] = []
    cost: list[float | None] = []
    net_position: list[float | None] = []
    net_change: list[float | None] = []
    unrealized_pnl: list[float | None] = []
    realized_pnl: list[float] = []
    retail_ratio: list[float | None] = []
    foreign_spot_net: list[float | None] = []

    for b in visible:
        d = b["date"]
        m = metrics_by_date.get(d)
        dates.append(d)
        candles.append({
            "open":   b.get("open"),
            "high":   b.get("high"),
            "low":    b.get("low"),
            "close":  b.get("close"),
            "volume": b.get("volume"),
        })
        cost.append(m["cost"] if m else None)
        net_position.append(m["net_position"] if m else None)
        net_change.append(m["net_change"] if m else None)
        unrealized_pnl.append(m["unrealized_pnl"] if m else None)
        realized_pnl.append(m["realized_pnl"] if m else 0.0)
        retail_ratio.append(retail_ratio_by_date.get(d))
        foreign_spot_net.append(spot_by_date.get(d))

    # 5) Settlement-date markers inside the visible window.
    settlement_dates = get_settlement_dates_in_range(
        "TX", window_start_str, today_str,
    )

    # 6) TXO options block — chart series projected onto the same date
    # timeline plus a per-date detail map for the breakdown table.
    txo_rows = get_institutional_options_range("TXO", window_start_str)
    options = build_options_block(dates, txo_rows)

    # 6b) Strike-level OI distribution for the latest trading day with
    # data. TAIFEX publishes this market-wide (no identity breakdown),
    # so we surface the full per-strike CALL/PUT histogram and let the
    # frontend default to the near-month monthly contract.
    strike_date = get_latest_txo_strike_oi_date("TXO")
    strike_rows = (
        get_txo_strike_oi_on_date("TXO", strike_date) if strike_date else []
    )
    options["oi_by_strike"] = build_strike_oi_block(strike_rows)

    return {
        "symbol":           "TX",
        "name":             "台指期 (TX) — 外資動向",
        "currency":         "TWD",
        "time_range":       time_range,
        "dates":            dates,
        "candles":          candles,
        "cost":             cost,
        "net_position":     net_position,
        "net_change":       net_change,
        "unrealized_pnl":   unrealized_pnl,
        "realized_pnl":     realized_pnl,
        "retail_ratio":     retail_ratio,
        "foreign_spot_net": foreign_spot_net,
        "settlement_dates": settlement_dates,
        "options":          options,
    }


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
