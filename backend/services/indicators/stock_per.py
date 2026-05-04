"""PER / PBR / Dividend Yield (stock daily)."""
from datetime import datetime, timedelta, timezone

from repositories.fundamentals import get_per_daily_range
from services.alert_registry import IndicatorSpec, register_indicator
from services.indicators._helpers import percentile_rank


def _get_history(ticker: str, n: int, *, field: str) -> list[float]:
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=max(n * 3 + 30, 60))).isoformat()
    rows = get_per_daily_range(ticker, since_date)
    values = [r[field] for r in rows if r[field] is not None]
    return values[-n:]


def _get_latest(ticker: str, *, field: str) -> float | None:
    history = _get_history(ticker, 1, field=field)
    return history[-1] if history else None


def _get_percentile(ticker: str, *, field: str) -> float | None:
    history = _get_history(ticker, 1825, field=field)
    if not history:
        return None
    return percentile_rank(history[-1], history)


_DAILY_CONDS = {
    "above", "below", "streak_above", "streak_below",
    "percentile_above", "percentile_below",
}


for _key, _label, _unit in (
    ("per",            "PER",   ""),
    ("pbr",            "PBR",   ""),
    ("dividend_yield", "殖利率", "%"),
):
    register_indicator(IndicatorSpec(
        key=_key,
        label=_label,
        unit=_unit,
        target_type="stock_indicator",
        supported_conditions=_DAILY_CONDS,
        get_latest_value=lambda t, f=_key: _get_latest(t, field=f),
        get_history=lambda t, n, f=_key: _get_history(t, n, field=f),
        get_percentile=lambda t, f=_key: _get_percentile(t, field=f),
    ))
