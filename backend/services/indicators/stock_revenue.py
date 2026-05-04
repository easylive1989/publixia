"""Stock monthly revenue (yoy-only)."""
from repositories.fundamentals import (
    get_latest_revenue_ym, get_revenue_monthly_range,
)
from services.alert_registry import IndicatorSpec, register_indicator


def _get_revenue_yoy(ticker: str) -> float | None:
    latest = get_latest_revenue_ym(ticker)
    if not latest:
        return None
    y, m = latest
    rows = get_revenue_monthly_range(ticker, y - 1, m)
    by_ym = {(r["year"], r["month"]): r["revenue"] for r in rows}
    cur = by_ym.get((y, m))
    prev = by_ym.get((y - 1, m))
    if cur is None or not prev:
        return None
    return round((cur - prev) / prev * 100, 2)


register_indicator(IndicatorSpec(
    key="revenue",
    label="月營收",
    unit="%",
    target_type="stock_indicator",
    supported_conditions={"yoy_above", "yoy_below"},
    get_latest_value=lambda _t: None,
    get_yoy=_get_revenue_yoy,
))
