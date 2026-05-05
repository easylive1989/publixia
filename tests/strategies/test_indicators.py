"""Indicator math: known input → known output."""
import math

import pytest

from services.strategy_dsl.indicators import (
    compute_indicator,
    required_lookback,
)
from services.strategy_dsl.models import (
    IndicatorSMA, IndicatorEMA, IndicatorRSI, IndicatorMACD,
    IndicatorBBands, IndicatorATR, IndicatorKD,
    IndicatorHighest, IndicatorLowest, IndicatorChangePct,
)


def _bars(closes, highs=None, lows=None, vols=None):
    """Build OHLCV bars where open=close=mid, highs/lows can be overridden."""
    out = []
    for i, c in enumerate(closes):
        h = highs[i] if highs else c + 1
        l = lows[i] if lows else c - 1
        v = vols[i] if vols else 1000
        out.append({"date": f"2026-01-{i+1:02d}",
                    "open": c, "high": h, "low": l, "close": c, "volume": v})
    return out


# ── SMA ───────────────────────────────────────────────────────────────

def test_sma_basic():
    bars = _bars([1, 2, 3, 4, 5])
    assert compute_indicator(IndicatorSMA(indicator="sma", n=5), bars) == 3.0


def test_sma_insufficient_data_returns_none():
    assert compute_indicator(IndicatorSMA(indicator="sma", n=5), _bars([1, 2])) is None


# ── EMA ───────────────────────────────────────────────────────────────

def test_ema_three_period_against_known_values():
    """EMA(3) of [1,2,3,4,5] with smoothing 2/(n+1)=0.5:
       ema[0]=1; ema[1]=2*0.5+1*0.5=1.5; ema[2]=3*0.5+1.5*0.5=2.25;
       ema[3]=4*0.5+2.25*0.5=3.125; ema[4]=5*0.5+3.125*0.5=4.0625
    """
    bars = _bars([1, 2, 3, 4, 5])
    got = compute_indicator(IndicatorEMA(indicator="ema", n=3), bars)
    assert math.isclose(got, 4.0625, rel_tol=1e-6)


# ── RSI ───────────────────────────────────────────────────────────────

def test_rsi_all_gains_returns_100():
    bars = _bars([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
    got = compute_indicator(IndicatorRSI(indicator="rsi", n=14), bars)
    assert math.isclose(got, 100.0, rel_tol=1e-6)


def test_rsi_all_losses_returns_zero():
    bars = _bars([15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
    got = compute_indicator(IndicatorRSI(indicator="rsi", n=14), bars)
    assert math.isclose(got, 0.0, abs_tol=1e-6)


# ── MACD ──────────────────────────────────────────────────────────────

def test_macd_outputs_three_keys():
    bars = _bars(list(range(1, 60)))
    spec = IndicatorMACD(indicator="macd", fast=12, slow=26, signal=9, output="macd")
    macd = compute_indicator(spec, bars)
    assert isinstance(macd, float)


def test_macd_hist_is_macd_minus_signal():
    bars = _bars(list(range(1, 60)))
    macd = compute_indicator(IndicatorMACD(indicator="macd", fast=12, slow=26, signal=9, output="macd"), bars)
    sig  = compute_indicator(IndicatorMACD(indicator="macd", fast=12, slow=26, signal=9, output="signal"), bars)
    hist = compute_indicator(IndicatorMACD(indicator="macd", fast=12, slow=26, signal=9, output="hist"), bars)
    assert math.isclose(hist, macd - sig, rel_tol=1e-6)


# ── BBands ────────────────────────────────────────────────────────────

def test_bbands_middle_equals_sma():
    bars = _bars([1, 2, 3, 4, 5, 6, 7, 8, 9, 10] * 3)
    mid = compute_indicator(IndicatorBBands(indicator="bbands", n=20, k=2.0, output="middle"), bars)
    sma = compute_indicator(IndicatorSMA(indicator="sma", n=20), bars)
    assert math.isclose(mid, sma, rel_tol=1e-9)


def test_bbands_upper_above_lower():
    bars = _bars([1, 2, 3, 4, 5, 6, 7, 8, 9, 10] * 3)
    upper = compute_indicator(IndicatorBBands(indicator="bbands", n=20, k=2.0, output="upper"), bars)
    lower = compute_indicator(IndicatorBBands(indicator="bbands", n=20, k=2.0, output="lower"), bars)
    assert upper > lower


# ── ATR ───────────────────────────────────────────────────────────────

def test_atr_constant_range():
    """If high-low is always 2 and there's no gap, ATR should converge to 2."""
    closes = list(range(1, 30))
    highs = [c + 1 for c in closes]
    lows  = [c - 1 for c in closes]
    bars = _bars(closes, highs, lows)
    got = compute_indicator(IndicatorATR(indicator="atr", n=14), bars)
    assert math.isclose(got, 2.0, abs_tol=0.5)


# ── KD (Stochastic) ──────────────────────────────────────────────────

def test_kd_at_high_returns_high_k():
    closes = [10] * 9 + [20]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    bars = _bars(closes, highs, lows)
    k = compute_indicator(IndicatorKD(indicator="kd", n=9, output="k"), bars)
    # Latest close is at the high of the window → %K should be near 100.
    assert k > 80


# ── Highest / Lowest ─────────────────────────────────────────────────

def test_highest_uses_high_column():
    closes = [10, 11, 12, 13, 14]
    highs  = [11, 99, 13, 14, 15]      # spike at i=1
    lows   = [9,  10, 11, 12, 13]
    bars = _bars(closes, highs, lows)
    got = compute_indicator(IndicatorHighest(indicator="highest", n=5), bars)
    assert got == 99


def test_lowest_uses_low_column():
    closes = [10, 11, 12, 13, 14]
    highs  = [11, 12, 13, 14, 15]
    lows   = [9,  -5, 11, 12, 13]      # plunge at i=1
    bars = _bars(closes, highs, lows)
    got = compute_indicator(IndicatorLowest(indicator="lowest", n=5), bars)
    assert got == -5


# ── change_pct ───────────────────────────────────────────────────────

def test_change_pct_basic():
    bars = _bars([100, 101, 102, 103, 110])
    got = compute_indicator(IndicatorChangePct(indicator="change_pct", n=4), bars)
    # (110 - 100) / 100 * 100 = 10.0
    assert math.isclose(got, 10.0, rel_tol=1e-6)


def test_change_pct_short_history_returns_none():
    bars = _bars([100])
    got = compute_indicator(IndicatorChangePct(indicator="change_pct", n=4), bars)
    assert got is None


# ── required_lookback ────────────────────────────────────────────────

def test_required_lookback_field():
    from services.strategy_dsl.models import FieldExpr
    assert required_lookback(FieldExpr(field="close")) == 1


def test_required_lookback_const():
    from services.strategy_dsl.models import ConstExpr
    assert required_lookback(ConstExpr(const=1)) == 0


def test_required_lookback_sma_uses_n():
    assert required_lookback(IndicatorSMA(indicator="sma", n=20)) == 20


def test_required_lookback_macd_uses_slow_plus_signal():
    spec = IndicatorMACD(indicator="macd", fast=12, slow=26, signal=9, output="macd")
    assert required_lookback(spec) == 26 + 9


def test_required_lookback_bbands_uses_n():
    assert required_lookback(IndicatorBBands(indicator="bbands", n=20, k=2.0, output="middle")) == 20


def test_required_lookback_change_pct_uses_n_plus_one():
    assert required_lookback(IndicatorChangePct(indicator="change_pct", n=4)) == 5
