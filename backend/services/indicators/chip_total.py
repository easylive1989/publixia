"""Indicator-level chip totals from chip_total fetcher."""
from repositories.indicators import get_latest_indicator
from services.alert_registry import IndicatorSpec, register_indicator
from services.indicators._helpers import fetch_indicator_history


def _make_chip_total_spec(key: str, label: str, unit: str) -> IndicatorSpec:
    return IndicatorSpec(
        key=key,
        label=label,
        unit=unit,
        target_type="indicator",
        supported_conditions={"above", "below", "streak_above", "streak_below"},
        get_latest_value=lambda _t, k=key: (
            (lambda r: r["value"] if r else None)(get_latest_indicator(k))
        ),
        get_history=lambda _t, n, k=key: fetch_indicator_history(k, n),
    )


for _key, _label, _unit in (
    ("margin_balance",     "台股融資餘額", "億元"),
    ("short_balance",      "台股融券餘額", "張"),
    ("short_margin_ratio", "台股券資比",   "%"),
    ("total_foreign_net",  "外資淨買超",   "億元"),
    ("total_trust_net",    "投信淨買超",   "億元"),
    ("total_dealer_net",   "自營商淨買超", "億元"),
):
    register_indicator(_make_chip_total_spec(_key, _label, _unit))
