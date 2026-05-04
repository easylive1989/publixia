"""Stock quarterly financial indicators (yoy-only)."""
from datetime import datetime, timezone

from repositories.fundamentals import get_financial_quarterly_range
from services.alert_registry import IndicatorSpec, register_indicator


_QUARTERLY_TYPES = {
    "q_eps":              ("income",    "EPS"),
    "q_revenue":          ("income",    "Revenue"),
    "q_operating_income": ("income",    "OperatingIncome"),
    "q_net_income":       ("income",    "IncomeAfterTaxes"),
    "q_operating_cf":     ("cash_flow", "CashFlowsFromOperatingActivities"),
}


def _get_quarterly_yoy(ticker: str, *, key: str) -> float | None:
    if key not in _QUARTERLY_TYPES:
        return None
    report_type, type_name = _QUARTERLY_TYPES[key]
    today = datetime.now(timezone.utc).date()
    since = today.replace(year=today.year - 3, month=1, day=1).isoformat()
    rows = get_financial_quarterly_range(ticker, report_type, since)
    same_type = [(r["date"], r["value"]) for r in rows
                 if r["type"] == type_name and r["value"] is not None]
    if not same_type:
        return None
    same_type.sort(key=lambda x: x[0])
    latest_date, latest_value = same_type[-1]

    dt = datetime.strptime(latest_date, "%Y-%m-%d")
    target_prev_date = f"{dt.year - 1}-{dt.month:02d}-{dt.day:02d}"
    prev_value = next((v for d, v in same_type if d == target_prev_date), None)
    if prev_value is None or prev_value == 0:
        return None
    return round((latest_value - prev_value) / prev_value * 100, 2)


_LABELS = {
    "q_eps":              "季 EPS",
    "q_revenue":          "季營收",
    "q_operating_income": "季營業利益",
    "q_net_income":       "季稅後淨利",
    "q_operating_cf":     "季營運現金流",
}

for _key, _label in _LABELS.items():
    register_indicator(IndicatorSpec(
        key=_key,
        label=_label,
        unit="%",
        target_type="stock_indicator",
        supported_conditions={"yoy_above", "yoy_below"},
        get_latest_value=lambda _t: None,
        get_yoy=lambda t, k=_key: _get_quarterly_yoy(t, key=k),
    ))
