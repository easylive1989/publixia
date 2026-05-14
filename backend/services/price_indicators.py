"""Close-series technical indicators (MA / RSI / MACD).

Used by the TX futures detail endpoint to enrich a candle response with
indicator overlays. Previously co-located with the (now-removed)
yfinance stock-history fetcher.
"""
from __future__ import annotations

import math


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _series_to_list(series) -> list[float | None]:
    return [_safe_float(v) for v in series.tolist()]


def compute_indicators(close) -> dict:
    """MA5/MA20/MA60, RSI14, MACD(12,26,9) from a pandas Close series."""
    ma5  = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi14 = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal

    return {
        "ma5":            _series_to_list(ma5),
        "ma20":           _series_to_list(ma20),
        "ma60":           _series_to_list(ma60),
        "rsi14":          _series_to_list(rsi14),
        "macd":           _series_to_list(macd),
        "macd_signal":    _series_to_list(macd_signal),
        "macd_histogram": _series_to_list(macd_hist),
    }
