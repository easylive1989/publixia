"""Assemble the 外資動向 composite payload from raw DB rows.

Single source of truth for the data shape exposed by
``GET /api/futures/tw/foreign-flow`` and consumed by the markdown
renderer. Returns ``None`` when there is no TX history in the window so
callers can map that to 404 / "no data" UI states.
"""
from datetime import date as _date, datetime, timedelta, timezone

from repositories.futures import get_futures_daily_range
from repositories.indicators import get_indicator_history
from repositories.institutional_futures import get_institutional_futures_range
from repositories.institutional_options import get_institutional_options_range
from repositories.txo_strike_oi import (
    get_latest_txo_strike_oi_date,
    get_txo_strike_oi_on_date,
)
from repositories.large_trader import get_large_trader_range
from services.foreign_futures_metrics import compute_metrics, compute_retail_ratio
from services.foreign_options_view import build_options_block
from services.futures_settlement import get_settlement_dates_in_range
from services.strike_oi_view import build_strike_oi_block


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


def assemble_foreign_flow_payload(
    time_range: str,
    today: _date | None = None,
) -> dict | None:
    """Compose the foreign-flow payload for ``time_range``.

    Returns ``None`` when no TX rows exist inside the lookback window —
    callers (route, markdown renderer) decide how to surface that.

    Raises ``ValueError`` if ``time_range`` is unknown so the route can
    translate it to HTTP 400.
    """
    if time_range not in RANGE_LOOKBACK_DAYS:
        raise ValueError(f"unknown time_range: {time_range}")

    if today is None:
        today = datetime.now(timezone.utc).astimezone().date()

    days = RANGE_LOOKBACK_DAYS[time_range]
    window_start  = today - timedelta(days=days)
    metrics_start = window_start - timedelta(days=_METRICS_WARMUP_DAYS)
    window_start_str  = window_start.strftime("%Y-%m-%d")
    metrics_start_str = metrics_start.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    # 1) K-line backbone
    tx_bars = get_futures_daily_range("TX", window_start_str)
    if not tx_bars:
        return None
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
    settlement_dates = get_settlement_dates_in_range(window_start_str, today_str)

    # 6) TXO options block — chart series projected onto the same
    # timeline plus a per-date detail map for the breakdown table.
    txo_rows = get_institutional_options_range("TXO", window_start_str)
    options = build_options_block(dates, txo_rows)

    # 6b) Strike-level OI distribution for the latest trading day with
    # data. TAIFEX publishes this market-wide (no identity breakdown).
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
