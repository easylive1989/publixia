"""Shared constants used by multiple route modules."""
from datetime import timedelta


RANGE_DELTAS: dict[str, timedelta] = {
    "1M": timedelta(days=30),
    "3M": timedelta(days=90),
    "6M": timedelta(days=180),
    "1Y": timedelta(days=365),
    "3Y": timedelta(days=1095),
}


INDICATOR_NAMES: list[str] = [
    "taiex", "fx", "fear_greed",
    "margin_balance", "short_balance", "short_margin_ratio",
    "total_foreign_net", "total_trust_net", "total_dealer_net",
    "ndc", "tw_volume", "tw_futures",
]


# Indicator key → scheduler job name responsible for refreshing it.
# Used by /api/dashboard to surface each card's next scheduled update time.
INDICATOR_JOB_MAP: dict[str, str] = {
    "taiex":              "taiex",
    "fx":                 "fx",
    "fear_greed":         "fear_greed",
    "margin_balance":     "chip_total",
    "short_balance":      "chip_total",
    "short_margin_ratio": "chip_total",
    "total_foreign_net":  "chip_total",
    "total_trust_net":    "chip_total",
    "total_dealer_net":   "chip_total",
    "ndc":                "ndc",
    "tw_volume":          "tw_volume",
    "tw_futures":         "tw_futures",
}
