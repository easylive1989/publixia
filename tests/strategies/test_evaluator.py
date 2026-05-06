"""Evaluator: hand-crafted bar histories → expected truth value."""
import pytest

from services.strategy_dsl.evaluator import (
    compute_expr, run_dsl, run_exit_dsl,
)
from services.strategy_dsl.models import (
    EntryDSL, ExitDSL, ExprNode,
)


def _bars(closes, highs=None, lows=None, vols=None):
    out = []
    for i, c in enumerate(closes):
        h = highs[i] if highs else c + 1
        lo = lows[i] if lows else c - 1
        v = vols[i] if vols else 1000
        out.append({"date": f"2026-01-{i+1:02d}",
                    "open": c, "high": h, "low": lo, "close": c, "volume": v})
    return out


def _entry(*conds) -> EntryDSL:
    return EntryDSL.model_validate({"version": 1, "all": list(conds)})


def _cond(left, op, right, n=None):
    d = {"left": left, "op": op, "right": right}
    if n is not None:
        d["n"] = n
    return d


# ── compute_expr ──────────────────────────────────────────────────────

def test_compute_expr_field():
    bars = _bars([10, 11, 12])
    e = ExprNode.validate_python({"field": "close"})
    assert compute_expr(e, bars) == 12


def test_compute_expr_const():
    e = ExprNode.validate_python({"const": 17000})
    assert compute_expr(e, []) == 17000


def test_compute_expr_var_entry_price_uses_arg():
    e = ExprNode.validate_python({"var": "entry_price"})
    assert compute_expr(e, [], entry_price=12345.67) == 12345.67


def test_compute_expr_var_without_entry_price_returns_none():
    e = ExprNode.validate_python({"var": "entry_price"})
    assert compute_expr(e, []) is None


def test_compute_expr_indicator_sma():
    bars = _bars([2, 4, 6, 8, 10])
    e = ExprNode.validate_python({"indicator": "sma", "n": 5})
    assert compute_expr(e, bars) == 6


# ── run_dsl: simple comparisons ───────────────────────────────────────

def test_run_dsl_close_above_const_true():
    bars = _bars([10, 11, 12])
    dsl = _entry(_cond({"field": "close"}, "gt", {"const": 10}))
    assert run_dsl(dsl, bars) is True


def test_run_dsl_close_above_const_false():
    bars = _bars([10, 11, 12])
    dsl = _entry(_cond({"field": "close"}, "gt", {"const": 99}))
    assert run_dsl(dsl, bars) is False


def test_run_dsl_two_conditions_anded():
    bars = _bars([10, 11, 12])
    dsl = _entry(
        _cond({"field": "close"}, "gt", {"const": 10}),
        _cond({"field": "close"}, "lt", {"const": 100}),
    )
    assert run_dsl(dsl, bars) is True


def test_run_dsl_short_history_returns_none():
    bars = _bars([10])
    dsl = _entry(_cond({"field": "close"}, "gt", {"indicator": "sma", "n": 5}))
    assert run_dsl(dsl, bars) is None


# ── run_dsl: cross_above / cross_below ────────────────────────────────

def test_run_dsl_cross_above_triggers_only_at_crossing():
    # close goes 5,5,5,12 ; const=10. Crossing happens between bar 2 and 3.
    bars = _bars([5, 5, 5, 12])
    dsl = _entry(_cond({"field": "close"}, "cross_above", {"const": 10}))
    assert run_dsl(dsl, bars) is True

    # If we look at the bar before the cross, no signal.
    assert run_dsl(dsl, bars[:3]) is False


def test_run_dsl_cross_below():
    bars = _bars([15, 12, 9])
    dsl = _entry(_cond({"field": "close"}, "cross_below", {"const": 10}))
    assert run_dsl(dsl, bars) is True


# ── run_dsl: streak_above / streak_below ──────────────────────────────

def test_run_dsl_streak_above_three_days():
    bars = _bars([5, 11, 12, 13])
    dsl = _entry(_cond(
        {"field": "close"}, "streak_above", {"const": 10}, n=3,
    ))
    assert run_dsl(dsl, bars) is True


def test_run_dsl_streak_above_breaks():
    bars = _bars([11, 9, 12, 13])
    dsl = _entry(_cond(
        {"field": "close"}, "streak_above", {"const": 10}, n=3,
    ))
    assert run_dsl(dsl, bars) is False


# ── run_exit_dsl: pct mode ───────────────────────────────────────────

def test_run_exit_pct_long_take_profit():
    """Long entry @ 100, +2% take profit → triggers when close >= 102."""
    pct = ExitDSL.validate_python({"version": 1, "type": "pct", "value": 2.0})
    bars = _bars([102])
    assert run_exit_dsl(pct, entry_price=100.0, direction="long", bars=bars,
                        kind="take_profit") is True


def test_run_exit_pct_long_stop_loss_close_above_threshold():
    """Long entry @ 100, 1% stop loss: triggers when close <= 99."""
    pct = ExitDSL.validate_python({"version": 1, "type": "pct", "value": 1.0})
    bars = _bars([99])
    assert run_exit_dsl(pct, entry_price=100.0, direction="long", bars=bars,
                        kind="stop_loss") is True


def test_run_exit_pct_short_take_profit():
    """Short entry @ 100, +2% take profit (price drop) → triggers when close <= 98."""
    pct = ExitDSL.validate_python({"version": 1, "type": "pct", "value": 2.0})
    bars = _bars([98])
    assert run_exit_dsl(pct, entry_price=100.0, direction="short", bars=bars,
                        kind="take_profit") is True


def test_run_exit_pct_no_trigger_when_within_band():
    pct = ExitDSL.validate_python({"version": 1, "type": "pct", "value": 2.0})
    bars = _bars([101])
    assert run_exit_dsl(pct, entry_price=100.0, direction="long", bars=bars,
                        kind="take_profit") is False


# ── run_exit_dsl: points mode ────────────────────────────────────────

def test_run_exit_points_long_take_profit():
    points = ExitDSL.validate_python({"version": 1, "type": "points", "value": 50})
    bars = _bars([100 + 50])
    assert run_exit_dsl(points, entry_price=100.0, direction="long", bars=bars,
                        kind="take_profit") is True


# ── run_exit_dsl: advanced (dsl) mode ────────────────────────────────

def test_run_exit_advanced_uses_entry_price_var():
    """Long: exit when close < entry_price (silly but tests the var path)."""
    spec = ExitDSL.validate_python({
        "version": 1, "type": "dsl",
        "all": [{"left": {"field": "close"}, "op": "lt",
                 "right": {"var": "entry_price"}}],
    })
    bars = _bars([99])
    assert run_exit_dsl(spec, entry_price=100.0, direction="long", bars=bars,
                        kind="stop_loss") is True
