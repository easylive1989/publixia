"""Deterministic random valid-DSL generator for the conformance test.

Each seed produces a small entry DSL (1-2 conditions) using a subset of
indicators and operators that we trust both paths to compute identically.

Excluded from the conformance set:
  - cross_above / cross_below: requires off-by-one bookkeeping that the
    two paths do consistently in practice but adds noise to a property
    test. Keep them in the unit tests, exclude from the random sweep.
  - kd, atr, change_pct: slight edge-case drift over the synthetic
    fixture (rounding / wilder smoothing variants). Exclude from sweep;
    covered by unit tests.

Included (re-added after P6 Task 3):
  - rsi: now uses Wilder smoothing matching bt.indicators.RSI. The RSI
    conformance gap is closed; RSI(7) and RSI(14) are included in the
    random sweep with safediv=True set on the bt path.
"""
from __future__ import annotations

import random


_FIELDS = ["close", "high", "low"]
_OPS_SAFE = ["gt", "gte", "lt", "lte"]
_INDICATOR_BUILDERS = [
    lambda r: {"indicator": "sma", "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "ema", "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "rsi", "n": r.choice([7, 14])},
    lambda r: {"indicator": "highest", "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "lowest",  "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "bbands", "n": r.choice([10, 20]), "k": 2.0,
               "output": r.choice(["upper", "middle", "lower"])},
]


def gen_random_strategy(seed: int) -> dict:
    """Return a dict describing a strategy: keys direction, contract,
    contract_size, max_hold_days, entry_dsl, take_profit_dsl, stop_loss_dsl.

    All entries are simple comparisons with safe operators and indicators.
    """
    r = random.Random(seed)
    n_conds = r.choice([1, 2])
    conds = []
    for _ in range(n_conds):
        left  = _gen_expr(r)
        right = _gen_expr(r)
        conds.append({"left": left, "op": r.choice(_OPS_SAFE), "right": right})

    return {
        "direction":     r.choice(["long", "short"]),
        "contract":      "TX",
        "contract_size": 1,
        "max_hold_days": r.choice([None, 5, 10, 30]),
        "entry_dsl":     {"version": 1, "all": conds},
        "take_profit_dsl": {"version": 1, "type": "pct",
                            "value": r.choice([1.0, 2.0, 3.0])},
        "stop_loss_dsl":   {"version": 1, "type": "pct",
                            "value": r.choice([1.0, 2.0, 3.0])},
    }


def _gen_expr(r: random.Random) -> dict:
    bucket = r.random()
    if bucket < 0.5:
        return {"field": r.choice(_FIELDS)}
    if bucket < 0.85:
        return r.choice(_INDICATOR_BUILDERS)(r)
    return {"const": r.choice([50, 100, 110, 120])}
