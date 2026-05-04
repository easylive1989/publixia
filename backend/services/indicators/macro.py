"""Indicator-level macro signals: TAIEX, FX, Fear & Greed, NDC."""
from repositories.indicators import get_latest_indicator
from services.alert_registry import IndicatorSpec, register_indicator
from services.indicators._helpers import fetch_indicator_history


def _make_macro_spec(key: str, label: str, unit: str) -> IndicatorSpec:
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
    ("taiex",      "加權指數",      "點"),
    ("fx",         "台幣兌美金",   "TWD"),
    ("fear_greed", "恐懼與貪婪指數", ""),
    ("ndc",        "國發會景氣指標", "分"),
):
    register_indicator(_make_macro_spec(_key, _label, _unit))
