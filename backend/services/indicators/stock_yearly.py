"""Stock yearly dividend indicators (yoy-only)."""
import re

from repositories.fundamentals import get_dividend_history
from services.alert_registry import IndicatorSpec, register_indicator


_FIELD_MAP = {
    "y_cash_dividend":  "cash_dividend",
    "y_stock_dividend": "stock_dividend",
}


def _get_yearly_yoy(ticker: str, *, key: str) -> float | None:
    if key not in _FIELD_MAP:
        return None
    field = _FIELD_MAP[key]
    raw_rows = get_dividend_history(ticker)
    if not raw_rows:
        return None

    by_year: dict[int, float] = {}
    for r in raw_rows:
        m = re.match(r"^(\d{2,3})年", r.get("year") or "")
        if not m:
            continue
        ce_year = int(m.group(1)) + 1911
        v = r.get(field) or 0
        by_year[ce_year] = by_year.get(ce_year, 0) + v

    if len(by_year) < 2:
        return None
    sorted_years = sorted(by_year.keys())
    latest_year = sorted_years[-1]
    prev_year = latest_year - 1
    cur = by_year.get(latest_year)
    prev = by_year.get(prev_year)
    if cur is None or not prev:
        return None
    return round((cur - prev) / prev * 100, 2)


_LABELS = {
    "y_cash_dividend":  "年度現金股利",
    "y_stock_dividend": "年度股票股利",
}

for _key, _label in _LABELS.items():
    register_indicator(IndicatorSpec(
        key=_key,
        label=_label,
        unit="%",
        target_type="stock_indicator",
        supported_conditions={"yoy_above", "yoy_below"},
        get_latest_value=lambda _t: None,
        get_yoy=lambda t, k=_key: _get_yearly_yoy(t, key=k),
    ))
