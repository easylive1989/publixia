"""Indicator math + lookback estimation.

All functions operate on a list of bar dicts sorted ascending by date.
Each bar must have at least: open, high, low, close, volume.
Latest bar is bars[-1]. Returning None means "insufficient history" and
is the engine's signal to skip evaluation for the day.

We deliberately avoid pandas here — the realtime evaluator runs once
per strategy per day on a single bar tail, and the overhead of a pandas
DataFrame would dominate. The Backtrader path uses bt.indicators.* which
have their own internal buffering.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from .models import (
    ConstExpr, FieldExpr, VarExpr,
    IndicatorSMA, IndicatorEMA, IndicatorRSI, IndicatorMACD,
    IndicatorBBands, IndicatorATR, IndicatorKD,
    IndicatorHighest, IndicatorLowest, IndicatorChangePct,
)


def _closes(bars: Sequence[dict]) -> np.ndarray:
    return np.asarray([b["close"] for b in bars], dtype=float)


def _highs(bars: Sequence[dict]) -> np.ndarray:
    return np.asarray([b["high"] for b in bars], dtype=float)


def _lows(bars: Sequence[dict]) -> np.ndarray:
    return np.asarray([b["low"] for b in bars], dtype=float)


def _ema(values: np.ndarray, n: int) -> np.ndarray:
    """Simple EMA with smoothing α=2/(n+1), seeded at values[0]."""
    if len(values) == 0:
        return values
    alpha = 2.0 / (n + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


# ── public API ──────────────────────────────────────────────────────

def compute_indicator(spec, bars: Sequence[dict]) -> float | None:
    """Return the latest value of `spec` over `bars`, or None if too short."""
    n_required = required_lookback(spec)
    if len(bars) < n_required:
        return None

    if isinstance(spec, IndicatorSMA):
        return float(_closes(bars)[-spec.n:].mean())

    if isinstance(spec, IndicatorEMA):
        return float(_ema(_closes(bars), spec.n)[-1])

    if isinstance(spec, IndicatorRSI):
        return _compute_rsi(_closes(bars), spec.n)

    if isinstance(spec, IndicatorMACD):
        return _compute_macd(_closes(bars), spec)

    if isinstance(spec, IndicatorBBands):
        return _compute_bbands(_closes(bars), spec)

    if isinstance(spec, IndicatorATR):
        return _compute_atr(bars, spec.n)

    if isinstance(spec, IndicatorKD):
        return _compute_kd(bars, spec)

    if isinstance(spec, IndicatorHighest):
        return float(_highs(bars)[-spec.n:].max())

    if isinstance(spec, IndicatorLowest):
        return float(_lows(bars)[-spec.n:].min())

    if isinstance(spec, IndicatorChangePct):
        closes = _closes(bars)
        prev = closes[-(spec.n + 1)]
        return float((closes[-1] - prev) / prev * 100.0)

    raise TypeError(f"unknown indicator spec: {type(spec).__name__}")


def required_lookback(expr) -> int:
    """Minimum bar count needed to evaluate `expr` once."""
    if isinstance(expr, FieldExpr):
        return 1
    if isinstance(expr, ConstExpr):
        return 0
    if isinstance(expr, VarExpr):
        return 0
    if isinstance(expr, IndicatorSMA):
        return expr.n
    if isinstance(expr, IndicatorEMA):
        return expr.n
    if isinstance(expr, IndicatorRSI):
        return expr.n + 1            # need n diffs → n+1 bars
    if isinstance(expr, IndicatorMACD):
        return expr.slow + expr.signal
    if isinstance(expr, IndicatorBBands):
        return expr.n
    if isinstance(expr, IndicatorATR):
        return expr.n + 1            # need n true ranges → n+1 bars
    if isinstance(expr, IndicatorKD):
        return expr.n
    if isinstance(expr, IndicatorHighest):
        return expr.n
    if isinstance(expr, IndicatorLowest):
        return expr.n
    if isinstance(expr, IndicatorChangePct):
        return expr.n + 1            # need close[-(n+1)]
    raise TypeError(f"unknown expr: {type(expr).__name__}")


# ── helpers ──────────────────────────────────────────────────────────

def _compute_rsi(closes: np.ndarray, n: int) -> float:
    diffs = np.diff(closes)
    gains = np.where(diffs > 0, diffs, 0.0)
    losses = np.where(diffs < 0, -diffs, 0.0)
    avg_gain = gains[-n:].mean()
    avg_loss = losses[-n:].mean()
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _compute_macd(closes: np.ndarray, spec: IndicatorMACD) -> float:
    fast_ema = _ema(closes, spec.fast)
    slow_ema = _ema(closes, spec.slow)
    macd_line = fast_ema - slow_ema
    if spec.output == "macd":
        return float(macd_line[-1])
    signal_line = _ema(macd_line, spec.signal)
    if spec.output == "signal":
        return float(signal_line[-1])
    return float(macd_line[-1] - signal_line[-1])


def _compute_bbands(closes: np.ndarray, spec: IndicatorBBands) -> float:
    window = closes[-spec.n:]
    mean = float(window.mean())
    if spec.output == "middle":
        return mean
    std = float(window.std(ddof=0))
    if spec.output == "upper":
        return mean + spec.k * std
    return mean - spec.k * std


def _compute_atr(bars: Sequence[dict], n: int) -> float | None:
    """Wilder-style smoothed true-range mean."""
    highs = _highs(bars)
    lows = _lows(bars)
    closes = _closes(bars)
    trs = []
    for i in range(1, len(bars)):
        prev_close = closes[i - 1]
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - prev_close),
            abs(lows[i] - prev_close),
        )
        trs.append(tr)
    if len(trs) < n:
        return None
    return float(np.mean(trs[-n:]))


def _compute_kd(bars: Sequence[dict], spec: IndicatorKD) -> float:
    """Plain Stochastic %K = (close - low_n) / (high_n - low_n) * 100;
    %D = 3-period SMA of %K. We compute %K over the last spec.n window."""
    window_high = max(b["high"] for b in bars[-spec.n:])
    window_low  = min(b["low"]  for b in bars[-spec.n:])
    if window_high == window_low:
        k = 50.0
    else:
        k = (bars[-1]["close"] - window_low) / (window_high - window_low) * 100.0
    if spec.output == "k":
        return float(k)
    # %D: 3-window average of recent %K values; fall back to k if too short.
    ks = []
    for end in range(len(bars) - 2, len(bars) + 1):
        if end < spec.n:
            continue
        h = max(b["high"] for b in bars[end - spec.n:end])
        lo = min(b["low"] for b in bars[end - spec.n:end])
        c = bars[end - 1]["close"]
        ks.append(50.0 if h == lo else (c - lo) / (h - lo) * 100.0)
    return float(np.mean(ks[-3:])) if ks else float(k)
