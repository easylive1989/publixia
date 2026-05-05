"""DSL evaluation against a bar history.

Returns True / False / None for each evaluation. None means "I refuse to
answer because the history is too short for the requested indicator(s)" —
the engine treats that as a no-fire and proceeds to the next strategy.
"""
from __future__ import annotations

from typing import Sequence

from .indicators import compute_indicator, required_lookback
from .models import (
    ConstExpr, FieldExpr, VarExpr, _IndicatorBase,
    DSLCondition, EntryDSL,
    ExitDSL_Pct, ExitDSL_Points, ExitDSL_Advanced,
)


# ── compute_expr ──────────────────────────────────────────────────────

def compute_expr(expr, bars: Sequence[dict],
                 *, entry_price: float | None = None) -> float | None:
    """Reduce an ExprNode to a float on the latest bar; None if data short."""
    if isinstance(expr, FieldExpr):
        if not bars:
            return None
        return float(bars[-1][expr.field])
    if isinstance(expr, ConstExpr):
        return float(expr.const)
    if isinstance(expr, VarExpr):
        if expr.var == "entry_price":
            return float(entry_price) if entry_price is not None else None
        return None
    if isinstance(expr, _IndicatorBase):
        return compute_indicator(expr, bars)
    raise TypeError(f"unknown expr: {type(expr).__name__}")


def _expr_lookback(expr) -> int:
    return required_lookback(expr)


# ── condition / DSL evaluation ───────────────────────────────────────

def _eval_condition(cond: DSLCondition, bars: Sequence[dict],
                    *, entry_price: float | None) -> bool | None:
    op = cond.op

    if op in ("gt", "gte", "lt", "lte"):
        l = compute_expr(cond.left,  bars, entry_price=entry_price)
        r = compute_expr(cond.right, bars, entry_price=entry_price)
        if l is None or r is None:
            return None
        if op == "gt":  return l >  r
        if op == "gte": return l >= r
        if op == "lt":  return l <  r
        return l <= r                 # lte

    if op in ("cross_above", "cross_below"):
        if len(bars) < 2:
            return None
        l_now  = compute_expr(cond.left,  bars,        entry_price=entry_price)
        r_now  = compute_expr(cond.right, bars,        entry_price=entry_price)
        l_prev = compute_expr(cond.left,  bars[:-1],   entry_price=entry_price)
        r_prev = compute_expr(cond.right, bars[:-1],   entry_price=entry_price)
        if any(v is None for v in (l_now, r_now, l_prev, r_prev)):
            return None
        if op == "cross_above":
            return l_now > r_now and l_prev <= r_prev
        return l_now < r_now and l_prev >= r_prev

    if op in ("streak_above", "streak_below"):
        n = cond.n or 1
        if len(bars) < n:
            return None
        for offset in range(n):
            tail = bars[: len(bars) - offset] if offset > 0 else bars
            l = compute_expr(cond.left,  tail, entry_price=entry_price)
            r = compute_expr(cond.right, tail, entry_price=entry_price)
            if l is None or r is None:
                return None
            if op == "streak_above" and not (l >= r):
                return False
            if op == "streak_below" and not (l <= r):
                return False
        return True

    raise ValueError(f"unknown op: {op}")


def run_dsl(dsl: EntryDSL, bars: Sequence[dict],
            *, entry_price: float | None = None) -> bool | None:
    """Evaluate the AND-list. Any None propagates; empty AND would be True
    but the model rejects min_length<1 so we never see it here."""
    seen_unknown = False
    for cond in dsl.all:
        result = _eval_condition(cond, bars, entry_price=entry_price)
        if result is None:
            seen_unknown = True
        elif result is False:
            return False
    return None if seen_unknown else True


# ── run_exit_dsl: handles three modes ────────────────────────────────

def run_exit_dsl(dsl, *, entry_price: float, direction: str,
                 bars: Sequence[dict], kind: str) -> bool | None:
    """`kind` is 'take_profit' or 'stop_loss' — only matters for pct/points
    sign convention. For 'dsl' mode the rule is inside the model itself.
    """
    if not bars:
        return None
    close = float(bars[-1]["close"])

    if isinstance(dsl, ExitDSL_Pct):
        return _check_simple_exit(close, entry_price, direction, kind,
                                  pct=dsl.value, points=None)
    if isinstance(dsl, ExitDSL_Points):
        return _check_simple_exit(close, entry_price, direction, kind,
                                  pct=None, points=dsl.value)
    if isinstance(dsl, ExitDSL_Advanced):
        return run_dsl(EntryDSL(version=1, all=dsl.all), bars,
                       entry_price=entry_price)
    raise TypeError(f"unknown exit DSL: {type(dsl).__name__}")


def _check_simple_exit(close: float, entry_price: float, direction: str,
                       kind: str, *, pct: float | None,
                       points: float | None) -> bool:
    """Compute the threshold and compare close to it.

    Sign convention:
        long  + take_profit  → close >= entry_price + offset
        long  + stop_loss    → close <= entry_price - offset
        short + take_profit  → close <= entry_price - offset
        short + stop_loss    → close >= entry_price + offset
    """
    if pct is not None:
        offset = entry_price * (pct / 100.0)
    else:
        offset = float(points)

    if direction == "long":
        if kind == "take_profit":
            return close >= entry_price + offset
        return close <= entry_price - offset
    # short
    if kind == "take_profit":
        return close <= entry_price - offset
    return close >= entry_price + offset
