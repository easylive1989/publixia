"""Stock chip daily indicators: foreign/trust/dealer net + margin/short balance."""
from datetime import datetime, timedelta, timezone

from repositories.chip import get_chip_daily_range
from services.alert_registry import IndicatorSpec, register_indicator


_NET_KEYS = {"foreign_net", "trust_net", "dealer_net"}


def _get_history(ticker: str, n: int, *, key: str) -> list[float]:
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=max(n * 3 + 30, 60))).isoformat()
    rows = get_chip_daily_range(ticker, since_date)
    if key in _NET_KEYS:
        bs_prefix = key[:-4]   # 'foreign_net' → 'foreign'
        values = []
        for r in rows:
            buy, sell = r[f"{bs_prefix}_buy"], r[f"{bs_prefix}_sell"]
            if buy is None or sell is None:
                values.append(None)
            else:
                values.append(buy - sell)
    else:  # margin_balance / short_balance
        values = [r[key] for r in rows]
    clean = [v for v in values if v is not None]
    return clean[-n:]


def _get_latest(ticker: str, *, key: str) -> float | None:
    history = _get_history(ticker, 1, key=key)
    return history[-1] if history else None


_CONDS = {"above", "below", "streak_above", "streak_below"}


_LABELS = {
    "foreign_net":      "外資淨買",
    "trust_net":        "投信淨買",
    "dealer_net":       "自營淨買",
    "margin_balance":   "融資餘額",
    "short_balance":    "融券餘額",
}

for _key, _label in _LABELS.items():
    register_indicator(IndicatorSpec(
        key=_key,
        label=_label,
        unit="",
        target_type="stock_indicator",
        supported_conditions=_CONDS,
        get_latest_value=lambda t, k=_key: _get_latest(t, key=k),
        get_history=lambda t, n, k=_key: _get_history(t, n, key=k),
    ))
