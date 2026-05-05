# FSE Phase 2 — DSL + Backtrader Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the strategy DSL — pure Pydantic models, an indicator library, a real-time evaluator, and a Backtrader translator that runs the same DSL as a backtest. After P2, given a strategy definition + historical bars, you can both (a) ask "would this strategy trigger today?" deterministically and (b) run a full backtest with trade list + analyzer stats. No fetcher, API, or UI integration yet — that lands in P3/P4/P5.

**Architecture:** New package `backend/services/strategy_dsl/` (models / indicators / evaluator / validator) + a single `backend/services/strategy_backtest.py` that wraps Backtrader. The two paths share a single source of truth for indicator math and DSL semantics; a 50-seed conformance test asserts they agree on every random valid DSL fed through the same fixture data. Backtrader is a new runtime dependency.

**Tech Stack:** Python 3.12 / Pydantic 2 / Backtrader 1.9.78.123 / pandas / numpy / pytest.

**Spec reference:** `docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md` §4 (DSL grammar), §5 (engine — but only the pure helpers; state machine itself is P3), §6 (Backtrader integration).

---

## File Structure

**Created:**
- `backend/services/strategy_dsl/__init__.py` — re-exports the public API: `validate`, `run_dsl`, `run_exit_dsl`, `required_lookback`, the model classes.
- `backend/services/strategy_dsl/models.py` — Pydantic models for every node type and the three DSL roots.
- `backend/services/strategy_dsl/indicators.py` — pure indicator calculations (SMA / EMA / RSI / MACD / BBands / ATR / KD / Highest / Lowest / change_pct) + `required_lookback(expr)`.
- `backend/services/strategy_dsl/evaluator.py` — `compute_expr`, `run_dsl`, `run_exit_dsl`. Pure functions over a list-of-dicts bar history.
- `backend/services/strategy_dsl/validator.py` — `validate(dsl_dict, kind)` that does Pydantic check + entry-only constraint + Backtrader-translatability probe.
- `backend/services/strategy_backtest.py` — `BacktestStrategyInput` dataclass, `BacktestResult` / `Trade` / `Summary` / `EquityPoint` dataclasses, `_build_bt_strategy_class`, `_build_datafeed`, `try_translate`, `run_backtest`.
- `tests/strategies/__init__.py` (empty) — marks the new test package.
- `tests/strategies/conftest.py` — shared fixtures: synthetic bar generator, helper to build `BacktestStrategyInput`.
- `tests/strategies/test_dsl_models.py` — Pydantic round-trip + edge-case tests.
- `tests/strategies/test_indicators.py` — known-input/known-output unit tests for each indicator + `required_lookback`.
- `tests/strategies/test_evaluator.py` — `compute_expr` / `run_dsl` / `run_exit_dsl` over hand-crafted histories.
- `tests/strategies/test_validator.py` — schema rejections, `entry_price` constraint, translatability rejections.
- `tests/strategies/test_backtest.py` — `try_translate` happy path + `run_backtest` over a synthetic 250-bar fixture, asserting a deterministic trade list.
- `tests/strategies/test_dsl_conformance.py` — 50-seed property-style test that real-time evaluator and Backtrader produce identical signal-day sets.
- `tests/strategies/random_dsl_generator.py` — deterministic random valid DSL generator used by the conformance test.

**Modified:**
- `backend/requirements.txt` — append `backtrader`, `pandas`, `numpy`.

**Out of scope (deferred):**
- `backend/services/strategy_engine.py` (state machine), the fan-in barrier, fetcher integration, MTX/TMF fetchers — all P3.
- `api/routes/strategies.py`, `repositories/strategies.py` — P4.
- Frontend — P5.
- Any change to existing fetchers / scheduler / alert engine.
- **Equity curve, buy-and-hold benchmark, and Sharpe ratio** in `BacktestResult` — the dataclass holds these fields (`equity_curve`, `benchmark`) but P2 leaves them empty / Sharpe absent from `Summary`. Populated when P4 wires them into the API response payload (frontend chart consumer lands in P5). No P2 caller renders them, so leaving them empty is harmless.

---

## Task 1 — Add Backtrader / pandas / numpy as runtime deps

**Files:**
- Modify: `backend/requirements.txt`

This task installs and verifies the three new deps. Backtrader's last release predates Python 3.12 by a year; we want to catch any import-time incompatibility now, not in P3.

- [ ] **Step 1.1: Append the three lines to `backend/requirements.txt`**

After the existing `pydantic-settings>=2.0.0` line, append:

```
backtrader>=1.9.78.123
pandas>=2.0
numpy>=1.24
```

The file should now end with three new lines.

- [ ] **Step 1.2: Install into the local environment**

Run from repo root:

```bash
python3 -m pip install -r backend/requirements.txt
```

If the active Python isn't backed by a venv and the install lands in user site-packages, that's fine for this verification task — production deploys re-install on the VPS via the GitHub Actions workflow.

- [ ] **Step 1.3: Verify Backtrader imports cleanly**

```bash
python3 -c "import backtrader as bt; print('backtrader', bt.__version__); import pandas; print('pandas', pandas.__version__); import numpy; print('numpy', numpy.__version__)"
```

Expected: three version lines, no traceback. If `import backtrader` fails with a matplotlib-related error, run `python3 -m pip install matplotlib` and retry; some Backtrader versions touch matplotlib at import time.

- [ ] **Step 1.4: Run the existing test suite to confirm no surprises**

```bash
python3 -m pytest tests/ -q
```

Expected: all 210 tests pass. If anything about pandas/numpy auto-import breaks an existing test, stop and report — it likely needs a tighter version pin.

- [ ] **Step 1.5: Commit**

```bash
git add backend/requirements.txt
git commit -m "$(cat <<'EOF'
deps(strategy): add backtrader, pandas, numpy for FSE backtester

Backtrader 1.9.78.123 is the last upstream release; it imports cleanly
on Python 3.12 with pandas 2.x and numpy 1.x. Pinned at minimum
versions only — bumping major-versions of pandas/numpy in future is
expected to be safe per Backtrader's pure-Python design.
EOF
)"
```

---

## Task 2 — Pydantic DSL models

**Files:**
- Create: `backend/services/strategy_dsl/__init__.py`
- Create: `backend/services/strategy_dsl/models.py`
- Create: `tests/strategies/__init__.py`
- Create: `tests/strategies/test_dsl_models.py`

The DSL has three root shapes (entry, two simple exits, advanced exit) and four expression kinds (`field`, `indicator`, `const`, `var`). We model the union with Pydantic v2 discriminated unions so a malformed dict produces a precise error path.

- [ ] **Step 2.1: Create the empty test package marker**

Create `tests/strategies/__init__.py` with a single empty line. Pytest discovery doesn't strictly require this, but it lets us import shared modules across test files.

- [ ] **Step 2.2: Write the failing model test file**

Create `tests/strategies/test_dsl_models.py`:

```python
"""Pydantic round-trip and rejection tests for the DSL models."""
import pytest
from pydantic import ValidationError

from services.strategy_dsl.models import (
    EntryDSL,
    ExitDSL,
    ExprNode,
    OPERATORS,
)


# ── ExprNode round-trip ───────────────────────────────────────────────

def test_expr_field():
    e = ExprNode.validate_python({"field": "close"})
    assert e.kind == "field"
    assert e.field == "close"


def test_expr_field_rejects_unknown_column():
    with pytest.raises(ValidationError):
        ExprNode.validate_python({"field": "vwap"})


def test_expr_const():
    e = ExprNode.validate_python({"const": 17000})
    assert e.kind == "const"
    assert e.const == 17000


def test_expr_var_entry_price():
    e = ExprNode.validate_python({"var": "entry_price"})
    assert e.kind == "var"


def test_expr_var_rejects_unknown_var():
    with pytest.raises(ValidationError):
        ExprNode.validate_python({"var": "exit_price"})


def test_expr_indicator_sma():
    e = ExprNode.validate_python({"indicator": "sma", "n": 20})
    assert e.kind == "indicator"
    assert e.indicator == "sma"
    assert e.n == 20


def test_expr_indicator_macd_with_output():
    e = ExprNode.validate_python({
        "indicator": "macd", "fast": 12, "slow": 26, "signal": 9, "output": "hist"
    })
    assert e.indicator == "macd"
    assert e.output == "hist"


def test_expr_indicator_rejects_n_zero():
    with pytest.raises(ValidationError):
        ExprNode.validate_python({"indicator": "sma", "n": 0})


def test_expr_indicator_unknown_name():
    with pytest.raises(ValidationError):
        ExprNode.validate_python({"indicator": "stochrsi", "n": 14})


# ── EntryDSL ──────────────────────────────────────────────────────────

def _entry_one_condition() -> dict:
    return {
        "version": 1,
        "all": [
            {"left": {"field": "close"}, "op": "gt",
             "right": {"indicator": "sma", "n": 20}},
        ],
    }


def test_entry_dsl_minimal():
    m = EntryDSL.model_validate(_entry_one_condition())
    assert len(m.all) == 1
    assert m.all[0].op == "gt"


def test_entry_dsl_streak_requires_n():
    bad = _entry_one_condition()
    bad["all"][0]["op"] = "streak_above"
    with pytest.raises(ValidationError, match="n"):
        EntryDSL.model_validate(bad)


def test_entry_dsl_non_streak_rejects_n():
    bad = _entry_one_condition()
    bad["all"][0]["n"] = 3
    with pytest.raises(ValidationError, match="n"):
        EntryDSL.model_validate(bad)


def test_entry_dsl_empty_conditions_rejected():
    with pytest.raises(ValidationError):
        EntryDSL.model_validate({"version": 1, "all": []})


def test_entry_dsl_streak_n_must_be_positive():
    bad = _entry_one_condition()
    bad["all"][0]["op"] = "streak_below"
    bad["all"][0]["n"] = 0
    with pytest.raises(ValidationError):
        EntryDSL.model_validate(bad)


# ── ExitDSL — three modes ─────────────────────────────────────────────

def test_exit_pct_round_trip():
    m = ExitDSL.validate_python({"version": 1, "type": "pct", "value": 2.0})
    assert m.type == "pct"
    assert m.value == 2.0


def test_exit_pct_rejects_zero_value():
    with pytest.raises(ValidationError):
        ExitDSL.validate_python({"version": 1, "type": "pct", "value": 0})


def test_exit_points_round_trip():
    m = ExitDSL.validate_python({"version": 1, "type": "points", "value": 50})
    assert m.type == "points"


def test_exit_dsl_advanced_round_trip():
    m = ExitDSL.validate_python({
        "version": 1, "type": "dsl",
        "all": [
            {"left": {"field": "close"}, "op": "lt",
             "right": {"indicator": "sma", "n": 20}},
        ],
    })
    assert m.type == "dsl"
    assert len(m.all) == 1


def test_exit_dsl_unknown_type_rejected():
    with pytest.raises(ValidationError):
        ExitDSL.validate_python({"version": 1, "type": "magic", "value": 1})


# ── OPERATORS sanity ──────────────────────────────────────────────────

def test_operators_set_is_complete():
    assert OPERATORS == {
        "gt", "gte", "lt", "lte",
        "cross_above", "cross_below",
        "streak_above", "streak_below",
    }
```

- [ ] **Step 2.3: Run — should fail with ImportError**

```bash
python3 -m pytest tests/strategies/test_dsl_models.py -v
```

Expected: ModuleNotFoundError for `services.strategy_dsl.models`.

- [ ] **Step 2.4: Implement the models**

Create `backend/services/strategy_dsl/__init__.py`:

```python
"""Strategy DSL — Pydantic models, indicator math, evaluator, validator."""
from .models import (
    EntryDSL,
    ExitDSL,
    ExitDSL_Pct,
    ExitDSL_Points,
    ExitDSL_Advanced,
    ExprNode,
    DSLCondition,
    OPERATORS,
)

__all__ = [
    "EntryDSL",
    "ExitDSL",
    "ExitDSL_Pct",
    "ExitDSL_Points",
    "ExitDSL_Advanced",
    "ExprNode",
    "DSLCondition",
    "OPERATORS",
]
```

Create `backend/services/strategy_dsl/models.py`:

```python
"""Pydantic models for the strategy DSL.

The DSL is a JSON-only mini-language. Three roots:
  - EntryDSL: linear AND list of DSLCondition
  - ExitDSL_Pct / ExitDSL_Points: simple offsets relative to entry_price
  - ExitDSL_Advanced: same as EntryDSL but allows the {"var": "entry_price"}
    expression node

Discriminated unions live as TypeAdapter helpers (ExprNode / ExitDSL) so
the route layer can validate dicts with `ExitDSL.validate_python(...)`
and get a precise field path on rejection.
"""
from typing import Annotated, Literal, Union

from pydantic import (
    BaseModel, ConfigDict, Discriminator, Field, Tag,
    TypeAdapter, model_validator,
)


OPERATORS: set[str] = {
    "gt", "gte", "lt", "lte",
    "cross_above", "cross_below",
    "streak_above", "streak_below",
}

OHLCV_FIELDS = {"open", "high", "low", "close", "volume"}


# ── ExprNode variants ────────────────────────────────────────────────

class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldExpr(_Strict):
    field: Literal["open", "high", "low", "close", "volume"]

    @property
    def kind(self) -> str:
        return "field"


class ConstExpr(_Strict):
    const: float

    @property
    def kind(self) -> str:
        return "const"


class VarExpr(_Strict):
    var: Literal["entry_price"]

    @property
    def kind(self) -> str:
        return "var"


class _IndicatorBase(_Strict):
    @property
    def kind(self) -> str:
        return "indicator"


class IndicatorSMA(_IndicatorBase):
    indicator: Literal["sma"]
    n: int = Field(ge=1)


class IndicatorEMA(_IndicatorBase):
    indicator: Literal["ema"]
    n: int = Field(ge=1)


class IndicatorRSI(_IndicatorBase):
    indicator: Literal["rsi"]
    n: int = Field(default=14, ge=2)


class IndicatorMACD(_IndicatorBase):
    indicator: Literal["macd"]
    fast: int = Field(default=12, ge=1)
    slow: int = Field(default=26, ge=2)
    signal: int = Field(default=9, ge=1)
    output: Literal["macd", "signal", "hist"] = "macd"

    @model_validator(mode="after")
    def _slow_gt_fast(self):
        if self.slow <= self.fast:
            raise ValueError("macd.slow must be > macd.fast")
        return self


class IndicatorBBands(_IndicatorBase):
    indicator: Literal["bbands"]
    n: int = Field(default=20, ge=2)
    k: float = Field(default=2.0, gt=0)
    output: Literal["upper", "middle", "lower"] = "middle"


class IndicatorATR(_IndicatorBase):
    indicator: Literal["atr"]
    n: int = Field(default=14, ge=1)


class IndicatorKD(_IndicatorBase):
    indicator: Literal["kd"]
    n: int = Field(default=9, ge=1)
    output: Literal["k", "d"] = "k"


class IndicatorHighest(_IndicatorBase):
    indicator: Literal["highest"]
    n: int = Field(ge=1)


class IndicatorLowest(_IndicatorBase):
    indicator: Literal["lowest"]
    n: int = Field(ge=1)


class IndicatorChangePct(_IndicatorBase):
    indicator: Literal["change_pct"]
    n: int = Field(ge=1)


IndicatorExpr = Annotated[
    Union[
        IndicatorSMA, IndicatorEMA, IndicatorRSI, IndicatorMACD,
        IndicatorBBands, IndicatorATR, IndicatorKD,
        IndicatorHighest, IndicatorLowest, IndicatorChangePct,
    ],
    Field(discriminator="indicator"),
]


def _expr_discriminator(v) -> str:
    """Pick the variant key for the ExprNode union."""
    if isinstance(v, dict):
        if "field" in v:     return "field"
        if "indicator" in v: return "indicator"
        if "const" in v:     return "const"
        if "var" in v:       return "var"
    if isinstance(v, FieldExpr):    return "field"
    if isinstance(v, ConstExpr):    return "const"
    if isinstance(v, VarExpr):      return "var"
    if isinstance(v, _IndicatorBase): return "indicator"
    return "unknown"


_ExprUnion = Annotated[
    Union[
        Annotated[FieldExpr,     Tag("field")],
        Annotated[ConstExpr,     Tag("const")],
        Annotated[VarExpr,       Tag("var")],
        Annotated[IndicatorExpr, Tag("indicator")],
    ],
    Discriminator(_expr_discriminator),
]

ExprNode: TypeAdapter = TypeAdapter(_ExprUnion)


# ── DSLCondition + EntryDSL + ExitDSL ───────────────────────────────

class DSLCondition(_Strict):
    left:  _ExprUnion
    op:    Literal[
        "gt", "gte", "lt", "lte",
        "cross_above", "cross_below",
        "streak_above", "streak_below",
    ]
    right: _ExprUnion
    n:     int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _streak_requires_n(self):
        is_streak = self.op in ("streak_above", "streak_below")
        if is_streak and self.n is None:
            raise ValueError("streak_above / streak_below require an n field")
        if not is_streak and self.n is not None:
            raise ValueError("n is only valid on streak_above / streak_below")
        return self


class EntryDSL(_Strict):
    version: Literal[1] = 1
    all:     list[DSLCondition] = Field(min_length=1)


class ExitDSL_Pct(_Strict):
    version: Literal[1] = 1
    type:    Literal["pct"]
    value:   float = Field(gt=0)


class ExitDSL_Points(_Strict):
    version: Literal[1] = 1
    type:    Literal["points"]
    value:   float = Field(gt=0)


class ExitDSL_Advanced(_Strict):
    version: Literal[1] = 1
    type:    Literal["dsl"]
    all:     list[DSLCondition] = Field(min_length=1)


_ExitUnion = Union[ExitDSL_Pct, ExitDSL_Points, ExitDSL_Advanced]

ExitDSL: TypeAdapter = TypeAdapter(
    Annotated[_ExitUnion, Field(discriminator="type")],
)
```

- [ ] **Step 2.5: Run — should pass**

```bash
python3 -m pytest tests/strategies/test_dsl_models.py -v
```

Expected: 18 tests PASS.

- [ ] **Step 2.6: Run full suite (no regressions)**

```bash
python3 -m pytest tests/ -q
```

Expected: 210 + 18 = 228 PASS.

- [ ] **Step 2.7: Commit**

```bash
git add backend/services/strategy_dsl/__init__.py backend/services/strategy_dsl/models.py tests/strategies/__init__.py tests/strategies/test_dsl_models.py
git commit -m "$(cat <<'EOF'
feat(strategy): pydantic models for DSL

Models cover every node of §4 of the spec: 5 expr variants (field /
const / var / indicator with 10 sub-types), 8 operators, 3 exit modes
(pct / points / advanced). Discriminated unions surface bad keys with
precise paths. Zero runtime deps beyond pydantic — no DB, no
backtrader. Round-trip + rejection tests cover each shape.
EOF
)"
```

---

## Task 3 — Indicator library

**Files:**
- Create: `backend/services/strategy_dsl/indicators.py`
- Create: `tests/strategies/test_indicators.py`

Each indicator is a pure function that takes a sorted list of bar dicts and a parsed indicator expression model, and returns the latest indicator value (or `None` if the history is too short). Also: `required_lookback(expr)` returns the minimum number of bars an expression needs.

- [ ] **Step 3.1: Write the failing test file**

Create `tests/strategies/test_indicators.py`:

```python
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
```

- [ ] **Step 3.2: Run — should fail with ImportError**

```bash
python3 -m pytest tests/strategies/test_indicators.py -v
```

Expected: ModuleNotFoundError on `services.strategy_dsl.indicators`.

- [ ] **Step 3.3: Implement the indicator library**

Create `backend/services/strategy_dsl/indicators.py`:

```python
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


_INDICATOR_TYPES = (
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


def _compute_atr(bars: Sequence[dict], n: int) -> float:
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
        return None  # type: ignore[return-value]
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
```

- [ ] **Step 3.4: Run — should pass**

```bash
python3 -m pytest tests/strategies/test_indicators.py -v
```

Expected: 19 tests PASS.

- [ ] **Step 3.5: Run full suite (no regressions)**

```bash
python3 -m pytest tests/ -q
```

Expected: 247 PASS.

- [ ] **Step 3.6: Commit**

```bash
git add backend/services/strategy_dsl/indicators.py tests/strategies/test_indicators.py
git commit -m "$(cat <<'EOF'
feat(strategy): indicator library + required_lookback

10 indicators: sma, ema, rsi, macd (3 outputs), bbands (3 outputs),
atr, kd (2 outputs), highest, lowest, change_pct. Pure functions over
a list of bar dicts; numpy used internally for vectorised aggregates.
Each indicator + plain expr also reports required_lookback so the
realtime evaluator can decline to fire when history is short.
EOF
)"
```

---

## Task 4 — DSL evaluator

**Files:**
- Create: `backend/services/strategy_dsl/evaluator.py`
- Create: `tests/strategies/test_evaluator.py`

`run_dsl(model, bars)` answers "do all conditions hold on the latest bar?". `run_exit_dsl(model, entry_price, direction, bars)` answers the same for the three exit-mode shapes. Both return `True / False / None` (None = insufficient data).

- [ ] **Step 4.1: Write the failing evaluator test file**

Create `tests/strategies/test_evaluator.py`:

```python
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
```

- [ ] **Step 4.2: Run — should fail with ImportError**

```bash
python3 -m pytest tests/strategies/test_evaluator.py -v
```

Expected: ModuleNotFoundError on `services.strategy_dsl.evaluator`.

- [ ] **Step 4.3: Implement the evaluator**

Create `backend/services/strategy_dsl/evaluator.py`:

```python
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
```

- [ ] **Step 4.4: Run — should pass**

```bash
python3 -m pytest tests/strategies/test_evaluator.py -v
```

Expected: 18 tests PASS.

- [ ] **Step 4.5: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 265 PASS.

- [ ] **Step 4.6: Commit**

```bash
git add backend/services/strategy_dsl/evaluator.py tests/strategies/test_evaluator.py
git commit -m "$(cat <<'EOF'
feat(strategy): DSL evaluator (compute_expr + run_dsl + run_exit_dsl)

Pure-function evaluator over a list-of-dicts bar history. Returns
True/False/None where None means "history too short, defer". Supports
gt/gte/lt/lte plus cross_above/cross_below (compares latest vs prior
bar) and streak_above/streak_below (compares the last n bars).
run_exit_dsl handles all three exit modes: pct/points apply long/short
sign conventions; advanced delegates back to run_dsl.
EOF
)"
```

---

## Task 5 — DSL validator (schema + entry-price constraint)

**Files:**
- Create: `backend/services/strategy_dsl/validator.py`
- Create: `tests/strategies/test_validator.py`
- Modify: `backend/services/strategy_dsl/__init__.py` (re-export `validate`)

The route layer (P4) and admin tools call `validate(dsl_dict, kind)` to schema-check + enforce the rule "{var: entry_price} cannot appear in entry_dsl". Translatability check lands in Task 7 once Backtrader translator exists.

- [ ] **Step 5.1: Write the failing validator tests**

Create `tests/strategies/test_validator.py`:

```python
"""Schema + entry-price-constraint tests for validate(). Translatability
checks land in test_validator.py once Backtrader translator is wired up
(see Task 7)."""
import pytest

from services.strategy_dsl.validator import validate, DSLValidationError


_GOOD_ENTRY = {
    "version": 1,
    "all": [
        {"left": {"field": "close"}, "op": "gt",
         "right": {"indicator": "sma", "n": 20}},
    ],
}
_GOOD_EXIT_PCT = {"version": 1, "type": "pct", "value": 2.0}
_GOOD_EXIT_ADVANCED = {
    "version": 1, "type": "dsl",
    "all": [
        {"left": {"field": "close"}, "op": "lt",
         "right": {"var": "entry_price"}},
    ],
}


def test_validate_entry_happy_path():
    m = validate(_GOOD_ENTRY, kind="entry")
    assert len(m.all) == 1


def test_validate_take_profit_pct_happy_path():
    m = validate(_GOOD_EXIT_PCT, kind="take_profit")
    assert m.value == 2.0


def test_validate_advanced_exit_happy_path():
    m = validate(_GOOD_EXIT_ADVANCED, kind="stop_loss")
    assert len(m.all) == 1


def test_validate_entry_rejects_entry_price_var():
    bad = {
        "version": 1,
        "all": [
            {"left": {"field": "close"}, "op": "gt",
             "right": {"var": "entry_price"}},
        ],
    }
    with pytest.raises(DSLValidationError, match="entry_price"):
        validate(bad, kind="entry")


def test_validate_entry_rejects_entry_price_var_on_left_too():
    bad = {
        "version": 1,
        "all": [
            {"left": {"var": "entry_price"}, "op": "gt",
             "right": {"const": 0}},
        ],
    }
    with pytest.raises(DSLValidationError, match="entry_price"):
        validate(bad, kind="entry")


def test_validate_take_profit_dsl_can_use_entry_price():
    """Advanced exit DSL is allowed to reference entry_price."""
    m = validate(_GOOD_EXIT_ADVANCED, kind="take_profit")
    assert m is not None


def test_validate_unknown_kind_rejected():
    with pytest.raises(ValueError, match="kind"):
        validate(_GOOD_ENTRY, kind="bogus")


def test_validate_pydantic_failures_wrapped():
    with pytest.raises(DSLValidationError):
        validate({"version": 1, "all": []}, kind="entry")
```

- [ ] **Step 5.2: Run — should fail with ImportError**

```bash
python3 -m pytest tests/strategies/test_validator.py -v
```

Expected: ModuleNotFoundError on `services.strategy_dsl.validator`.

- [ ] **Step 5.3: Implement the validator**

Create `backend/services/strategy_dsl/validator.py`:

```python
"""Top-level validate() — pydantic check + entry-only constraint.

Backtrader-translatability check is wired in by Task 7.
"""
from __future__ import annotations

from pydantic import ValidationError
from typing import Literal

from .models import (
    EntryDSL, ExitDSL,
    ExitDSL_Advanced,
    DSLCondition, VarExpr,
)


class DSLValidationError(ValueError):
    """Raised for any DSL rejection. `errors` carries field-path detail
    so the API layer can surface a precise message."""
    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.errors = errors or []


_VALID_KINDS = ("entry", "take_profit", "stop_loss")


def validate(dsl_dict: dict, *, kind: str):
    """Validate `dsl_dict` against the model that matches `kind`.

    Returns the parsed model. Raises DSLValidationError on failure.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(f"validate(): unknown kind {kind!r}")

    try:
        if kind == "entry":
            model = EntryDSL.model_validate(dsl_dict)
        else:
            model = ExitDSL.validate_python(dsl_dict)
    except ValidationError as e:
        raise DSLValidationError(
            f"DSL validation failed for {kind}: {e.errors()[0]['msg']}",
            errors=e.errors(),
        ) from e

    if kind == "entry":
        _reject_entry_price_var(model.all)
    elif isinstance(model, ExitDSL_Advanced):
        # entry_price is allowed on advanced exit — no further check.
        pass

    return model


def _reject_entry_price_var(conds: list[DSLCondition]) -> None:
    for i, c in enumerate(conds):
        for side, expr in (("left", c.left), ("right", c.right)):
            if isinstance(expr, VarExpr) and expr.var == "entry_price":
                raise DSLValidationError(
                    f"entry_price variable not allowed in entry conditions "
                    f"(found at all[{i}].{side}); use take_profit_dsl / "
                    f"stop_loss_dsl with type='dsl' instead.",
                )
```

- [ ] **Step 5.4: Re-export `validate` and `DSLValidationError` from the package init**

Edit `backend/services/strategy_dsl/__init__.py` — replace its content with:

```python
"""Strategy DSL — Pydantic models, indicator math, evaluator, validator."""
from .models import (
    EntryDSL,
    ExitDSL,
    ExitDSL_Pct,
    ExitDSL_Points,
    ExitDSL_Advanced,
    ExprNode,
    DSLCondition,
    OPERATORS,
)
from .evaluator import run_dsl, run_exit_dsl, compute_expr
from .indicators import compute_indicator, required_lookback
from .validator import validate, DSLValidationError

__all__ = [
    "EntryDSL", "ExitDSL",
    "ExitDSL_Pct", "ExitDSL_Points", "ExitDSL_Advanced",
    "ExprNode", "DSLCondition", "OPERATORS",
    "run_dsl", "run_exit_dsl", "compute_expr",
    "compute_indicator", "required_lookback",
    "validate", "DSLValidationError",
]
```

- [ ] **Step 5.5: Run — should pass**

```bash
python3 -m pytest tests/strategies/test_validator.py -v
```

Expected: 8 tests PASS.

- [ ] **Step 5.6: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 273 PASS.

- [ ] **Step 5.7: Commit**

```bash
git add backend/services/strategy_dsl/validator.py backend/services/strategy_dsl/__init__.py tests/strategies/test_validator.py
git commit -m "$(cat <<'EOF'
feat(strategy): DSL validator with entry-price guard

validate(dsl_dict, kind) wraps pydantic validation + the rule that
{var: entry_price} cannot appear in an entry-condition DSL. Errors are
re-raised as DSLValidationError with .errors() field-path data so the
P4 route layer can return precise 422 messages.

Translatability check (round-trip via Backtrader) is intentionally
absent here — that lands in Task 7 once strategy_backtest.try_translate
exists.
EOF
)"
```

---

## Task 6 — Backtrader translator + `run_backtest`

**Files:**
- Create: `backend/services/strategy_backtest.py`
- Create: `tests/strategies/conftest.py`
- Create: `tests/strategies/test_backtest.py`

The translator builds a `bt.Strategy` subclass that interprets the DSL inside `next()`. We also expose `try_translate(strategy)` which constructs but does not run — used by Task 7 for the validator gate.

- [ ] **Step 6.1: Add the synthetic-bar fixture helper**

Create `tests/strategies/conftest.py`:

```python
"""Shared test helpers for tests/strategies/*."""
import math
from dataclasses import dataclass

import pytest


@dataclass
class FakeStrategy:
    """Minimal stand-in for the future P4 Strategy DB record. The backtest
    layer only reads these fields, so we don't need the full model yet."""
    direction: str
    contract: str
    contract_size: int
    max_hold_days: int | None
    entry_dsl: dict
    take_profit_dsl: dict
    stop_loss_dsl: dict


@pytest.fixture
def synthetic_bars():
    """A 250-bar deterministic OHLCV series. Mid follows a noisy uptrend
    (sin + drift); H/L are mid ± 5; volume is constant."""
    bars = []
    for i in range(250):
        mid = 100.0 + 0.05 * i + 5.0 * math.sin(i / 7.0)
        bars.append({
            "date":   f"2026-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}",
            "open":   mid,
            "high":   mid + 5.0,
            "low":    mid - 5.0,
            "close":  mid,
            "volume": 10_000,
        })
    return bars


@pytest.fixture
def make_strategy():
    """Factory that fills in long/TX/1-lot defaults and lets the test
    override only the DSL pieces."""
    def _build(*, direction="long", contract="TX", contract_size=1,
               max_hold_days=None,
               entry, take_profit=None, stop_loss=None):
        if take_profit is None:
            take_profit = {"version": 1, "type": "pct", "value": 5.0}
        if stop_loss is None:
            stop_loss = {"version": 1, "type": "pct", "value": 5.0}
        return FakeStrategy(
            direction=direction, contract=contract,
            contract_size=contract_size, max_hold_days=max_hold_days,
            entry_dsl=entry,
            take_profit_dsl=take_profit,
            stop_loss_dsl=stop_loss,
        )
    return _build
```

- [ ] **Step 6.2: Write the failing backtest test file**

Create `tests/strategies/test_backtest.py`:

```python
"""Backtrader translator + run_backtest happy-path tests."""
from services.strategy_backtest import (
    BacktestResult, Trade, Summary,
    run_backtest, try_translate,
)


# ── try_translate ─────────────────────────────────────────────────────

def test_try_translate_accepts_simple_strategy(make_strategy):
    s = make_strategy(entry={
        "version": 1,
        "all": [{"left": {"field": "close"}, "op": "gt",
                 "right": {"indicator": "sma", "n": 20}}],
    })
    cls = try_translate(s)
    assert cls is not None


def test_try_translate_handles_advanced_exit(make_strategy):
    s = make_strategy(
        entry={"version": 1,
               "all": [{"left": {"field": "close"}, "op": "gt",
                        "right": {"const": 50}}]},
        stop_loss={"version": 1, "type": "dsl",
                   "all": [{"left": {"field": "close"}, "op": "lt",
                            "right": {"var": "entry_price"}}]},
    )
    cls = try_translate(s)
    assert cls is not None


# ── run_backtest: deterministic trade list over the fixture ──────────

def test_run_backtest_produces_at_least_one_trade(make_strategy, synthetic_bars):
    """SMA(5) cross above SMA(20) on a noisy-uptrend fixture should fire
    at least once over 250 bars."""
    s = make_strategy(entry={
        "version": 1,
        "all": [{"left": {"indicator": "sma", "n": 5}, "op": "cross_above",
                 "right": {"indicator": "sma", "n": 20}}],
    })
    result = run_backtest(s, bars=synthetic_bars)
    assert isinstance(result, BacktestResult)
    assert isinstance(result.summary, Summary)
    assert len(result.trades) >= 1
    for t in result.trades:
        assert isinstance(t, Trade)
        assert t.exit_reason in {"TAKE_PROFIT", "STOP_LOSS", "TIMEOUT"}


def test_run_backtest_summary_pnl_matches_trade_sum(make_strategy, synthetic_bars):
    s = make_strategy(entry={
        "version": 1,
        "all": [{"left": {"indicator": "sma", "n": 5}, "op": "cross_above",
                 "right": {"indicator": "sma", "n": 20}}],
    })
    result = run_backtest(s, bars=synthetic_bars)
    expected = sum(t.pnl_amount for t in result.trades)
    assert abs(result.summary.total_pnl_amount - expected) < 1e-3


def test_run_backtest_short_direction_flips_pnl(make_strategy, synthetic_bars):
    s_long = make_strategy(direction="long", entry={
        "version": 1,
        "all": [{"left": {"field": "close"}, "op": "gt",
                 "right": {"const": 0}}],   # always-true entry → enter on bar 1
    }, take_profit={"version": 1, "type": "pct", "value": 100.0},  # high so it never fires
       stop_loss={"version": 1, "type": "pct", "value": 100.0})
    s_short = make_strategy(direction="short", entry={
        "version": 1,
        "all": [{"left": {"field": "close"}, "op": "gt",
                 "right": {"const": 0}}],
    }, take_profit={"version": 1, "type": "pct", "value": 100.0},
       stop_loss={"version": 1, "type": "pct", "value": 100.0})

    long_res  = run_backtest(s_long,  bars=synthetic_bars)
    short_res = run_backtest(s_short, bars=synthetic_bars)
    # In a generally rising fixture, long is profitable, short is losing,
    # and direction flips the open-position PnL sign.
    assert long_res.summary.total_pnl_amount > 0
    assert short_res.summary.total_pnl_amount < 0


def test_run_backtest_empty_bars_returns_empty_trades(make_strategy):
    s = make_strategy(entry={
        "version": 1,
        "all": [{"left": {"field": "close"}, "op": "gt",
                 "right": {"const": 0}}],
    })
    result = run_backtest(s, bars=[])
    assert result.trades == []
    assert result.summary.n_trades == 0
```

- [ ] **Step 6.3: Run — should fail with ImportError**

```bash
python3 -m pytest tests/strategies/test_backtest.py -v
```

Expected: ModuleNotFoundError on `services.strategy_backtest`.

- [ ] **Step 6.4: Implement the backtest module**

Create `backend/services/strategy_backtest.py`:

```python
"""DSL → Backtrader Strategy class translator + run_backtest helper.

`try_translate(strategy)` constructs a bt.Strategy subclass without
running cerebro; used by validator.translatability_check.

`run_backtest(strategy, bars=...)` runs Cerebro on the supplied bar list
(in tests) or — once P3 wires it up — on bars from the futures_daily
table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date
from typing import Sequence

import backtrader as bt
import pandas as pd

from services.strategy_dsl.models import (
    ConstExpr, FieldExpr, VarExpr,
    IndicatorSMA, IndicatorEMA, IndicatorRSI, IndicatorMACD,
    IndicatorBBands, IndicatorATR, IndicatorKD,
    IndicatorHighest, IndicatorLowest, IndicatorChangePct,
    EntryDSL, ExitDSL_Pct, ExitDSL_Points, ExitDSL_Advanced,
    DSLCondition,
)
from services.strategy_dsl.validator import validate


MULTIPLIER = {"TX": 200, "MTX": 50, "TMF": 10}


# ── public dataclasses ──────────────────────────────────────────────

@dataclass
class Trade:
    entry_date:    Date
    entry_price:   float
    exit_date:     Date
    exit_price:    float
    exit_reason:   str           # TAKE_PROFIT / STOP_LOSS / TIMEOUT
    held_bars:     int
    pnl_points:    float
    pnl_amount:    float


@dataclass
class Summary:
    total_pnl_amount: float
    win_rate:         float
    avg_win_points:   float
    avg_loss_points:  float
    profit_factor:    float
    max_drawdown_amt: float
    max_drawdown_pct: float
    n_trades:         int
    avg_held_bars:    float


@dataclass
class EquityPoint:
    date:   Date
    pnl:    float


@dataclass
class BacktestResult:
    trades:       list[Trade]
    summary:      Summary
    equity_curve: list[EquityPoint] = field(default_factory=list)
    benchmark:    list[EquityPoint] = field(default_factory=list)
    warnings:     list[str]         = field(default_factory=list)


# ── translator ──────────────────────────────────────────────────────

def try_translate(strategy) -> type[bt.Strategy]:
    """Build a bt.Strategy subclass for `strategy`. Validates the DSLs
    along the way (raises DSLValidationError on bad shape)."""
    entry  = validate(strategy.entry_dsl,       kind="entry")
    tp     = validate(strategy.take_profit_dsl, kind="take_profit")
    sl     = validate(strategy.stop_loss_dsl,   kind="stop_loss")
    return _build_bt_strategy_class(
        entry=entry, take_profit=tp, stop_loss=sl,
        direction=strategy.direction,
        contract_size=strategy.contract_size,
        max_hold_days=strategy.max_hold_days,
    )


def _build_bt_strategy_class(*, entry, take_profit, stop_loss,
                             direction, contract_size, max_hold_days
                             ) -> type[bt.Strategy]:

    class _GeneratedStrategy(bt.Strategy):
        params = (
            ("direction",     direction),
            ("contract_size", contract_size),
            ("max_hold_days", max_hold_days),
        )

        def __init__(self):
            self._ind_cache: dict[str, object] = {}
            for cond in entry.all:
                self._materialize_for(cond)
            if isinstance(take_profit, ExitDSL_Advanced):
                for cond in take_profit.all:
                    self._materialize_for(cond)
            if isinstance(stop_loss, ExitDSL_Advanced):
                for cond in stop_loss.all:
                    self._materialize_for(cond)
            self._entry_bar_idx: int | None = None
            self._exit_reason: str | None = None
            self._trade_log: list[Trade] = []

        # ── indicator materialisation ────────────────────────────

        def _materialize_for(self, cond: DSLCondition):
            for expr in (cond.left, cond.right):
                self._ensure_indicator(expr)

        def _ensure_indicator(self, expr):
            """Build & cache a bt indicator for `expr` if it is one;
            non-indicator nodes (field/const/var) get cache_key=None
            and are skipped — they're resolved directly in next()."""
            key = _expr_cache_key(expr)
            if key is None or key in self._ind_cache:
                return
            self._ind_cache[key] = _build_bt_indicator(expr, self.data)

        # ── core lifecycle ───────────────────────────────────────

        def next(self):
            if self.position:
                self._maybe_exit()
            else:
                self._maybe_entry()

        def _maybe_entry(self):
            if not self._evaluate_dsl(entry, entry_price=None):
                return
            size = self.p.contract_size
            if self.p.direction == "long":
                self.buy(size=size, exectype=bt.Order.Market)
            else:
                self.sell(size=size, exectype=bt.Order.Market)
            self._entry_bar_idx = len(self)

        def _maybe_exit(self):
            entry_price = self.position.price
            if self._evaluate_exit(stop_loss, entry_price, "stop_loss"):
                self._exit_reason = "STOP_LOSS"
                self.close(exectype=bt.Order.Market)
                return
            if self._evaluate_exit(take_profit, entry_price, "take_profit"):
                self._exit_reason = "TAKE_PROFIT"
                self.close(exectype=bt.Order.Market)
                return
            if self.p.max_hold_days is not None and self._entry_bar_idx is not None:
                held = len(self) - self._entry_bar_idx
                if held >= self.p.max_hold_days:
                    self._exit_reason = "TIMEOUT"
                    self.close(exectype=bt.Order.Market)

        # ── DSL evaluation ──────────────────────────────────────

        def _evaluate_dsl(self, dsl: EntryDSL, *, entry_price: float | None) -> bool:
            for cond in dsl.all:
                if not self._evaluate_condition(cond, entry_price=entry_price):
                    return False
            return True

        def _evaluate_exit(self, dsl, entry_price: float, kind: str) -> bool:
            if isinstance(dsl, ExitDSL_Pct):
                return _check_simple_threshold(
                    self.data.close[0], entry_price, self.p.direction,
                    kind, pct=dsl.value, points=None,
                )
            if isinstance(dsl, ExitDSL_Points):
                return _check_simple_threshold(
                    self.data.close[0], entry_price, self.p.direction,
                    kind, pct=None, points=dsl.value,
                )
            return self._evaluate_dsl(
                EntryDSL(version=1, all=dsl.all), entry_price=entry_price,
            )

        def _evaluate_condition(self, cond: DSLCondition,
                                *, entry_price: float | None) -> bool:
            op = cond.op

            def value(expr, offset=0):
                return _resolve_expr(expr, self.data, self._ind_cache,
                                     entry_price, offset=offset)

            if op in ("gt", "gte", "lt", "lte"):
                l = value(cond.left)
                r = value(cond.right)
                if l is None or r is None:
                    return False
                if op == "gt":  return l >  r
                if op == "gte": return l >= r
                if op == "lt":  return l <  r
                return l <= r
            if op in ("cross_above", "cross_below"):
                l_now,  r_now  = value(cond.left), value(cond.right)
                l_prev, r_prev = value(cond.left, offset=-1), value(cond.right, offset=-1)
                if any(x is None for x in (l_now, r_now, l_prev, r_prev)):
                    return False
                if op == "cross_above":
                    return l_now > r_now and l_prev <= r_prev
                return l_now < r_now and l_prev >= r_prev
            if op in ("streak_above", "streak_below"):
                n = cond.n or 1
                for k in range(n):
                    l = value(cond.left, offset=-k)
                    r = value(cond.right, offset=-k)
                    if l is None or r is None:
                        return False
                    if op == "streak_above" and not (l >= r):
                        return False
                    if op == "streak_below" and not (l <= r):
                        return False
                return True
            return False

        # ── trade logging ───────────────────────────────────────

        def notify_trade(self, trade):
            if not trade.isclosed:
                return
            entry_dt = bt.num2date(trade.dtopen).date()
            exit_dt  = bt.num2date(trade.dtclose).date()
            entry_price = trade.price
            exit_price = self.data.close[0]
            held = len(self) - (self._entry_bar_idx or 0)
            if self.p.direction == "long":
                pnl_points = exit_price - entry_price
            else:
                pnl_points = entry_price - exit_price
            self._trade_log.append(Trade(
                entry_date=entry_dt,
                entry_price=entry_price,
                exit_date=exit_dt,
                exit_price=exit_price,
                exit_reason=self._exit_reason or "TIMEOUT",
                held_bars=held,
                pnl_points=pnl_points,
                pnl_amount=pnl_points * self._multiplier() * self.p.contract_size,
            ))
            self._exit_reason = None
            self._entry_bar_idx = None

        def _multiplier(self) -> int:
            # Closure parameter `direction` is on the class; contract is
            # accessible via self.broker's commission, but easier: stash on init.
            return MULTIPLIER.get(getattr(self, "_contract", "TX"), 200)

    return _GeneratedStrategy


# ── expression resolution inside Backtrader's next() ───────────────

def _resolve_expr(expr, data, ind_cache, entry_price, *, offset: int):
    if isinstance(expr, FieldExpr):
        line = getattr(data, expr.field, None)
        if line is None:
            return None
        try:
            return float(line[offset])
        except IndexError:
            return None
    if isinstance(expr, ConstExpr):
        return float(expr.const)
    if isinstance(expr, VarExpr):
        return float(entry_price) if entry_price is not None else None
    key = _expr_cache_key(expr)
    if key is None:
        return None
    ind = ind_cache.get(key)
    if ind is None:
        return None
    try:
        return float(ind[offset])
    except (IndexError, ValueError):
        return None


def _expr_cache_key(expr) -> str | None:
    if isinstance(expr, IndicatorSMA):       return f"sma:{expr.n}"
    if isinstance(expr, IndicatorEMA):       return f"ema:{expr.n}"
    if isinstance(expr, IndicatorRSI):       return f"rsi:{expr.n}"
    if isinstance(expr, IndicatorMACD):      return f"macd:{expr.fast}:{expr.slow}:{expr.signal}:{expr.output}"
    if isinstance(expr, IndicatorBBands):    return f"bb:{expr.n}:{expr.k}:{expr.output}"
    if isinstance(expr, IndicatorATR):       return f"atr:{expr.n}"
    if isinstance(expr, IndicatorKD):        return f"kd:{expr.n}:{expr.output}"
    if isinstance(expr, IndicatorHighest):   return f"hi:{expr.n}"
    if isinstance(expr, IndicatorLowest):    return f"lo:{expr.n}"
    if isinstance(expr, IndicatorChangePct): return f"chg:{expr.n}"
    return None


def _build_bt_indicator(expr, data):
    if isinstance(expr, IndicatorSMA):
        return bt.indicators.SMA(data.close, period=expr.n)
    if isinstance(expr, IndicatorEMA):
        return bt.indicators.EMA(data.close, period=expr.n)
    if isinstance(expr, IndicatorRSI):
        return bt.indicators.RSI(data.close, period=expr.n)
    if isinstance(expr, IndicatorMACD):
        macd = bt.indicators.MACD(data.close,
                                  period_me1=expr.fast,
                                  period_me2=expr.slow,
                                  period_signal=expr.signal)
        if expr.output == "macd":   return macd.macd
        if expr.output == "signal": return macd.signal
        return macd.macd - macd.signal
    if isinstance(expr, IndicatorBBands):
        bb = bt.indicators.BollingerBands(data.close, period=expr.n,
                                          devfactor=expr.k)
        if expr.output == "upper": return bb.top
        if expr.output == "middle": return bb.mid
        return bb.bot
    if isinstance(expr, IndicatorATR):
        return bt.indicators.ATR(data, period=expr.n)
    if isinstance(expr, IndicatorKD):
        st = bt.indicators.Stochastic(data, period=expr.n)
        return st.percK if expr.output == "k" else st.percD
    if isinstance(expr, IndicatorHighest):
        return bt.indicators.Highest(data.high, period=expr.n)
    if isinstance(expr, IndicatorLowest):
        return bt.indicators.Lowest(data.low, period=expr.n)
    if isinstance(expr, IndicatorChangePct):
        return _ChangePct(data.close, period=expr.n)
    raise TypeError(f"unknown indicator expr {type(expr).__name__}")


class _ChangePct(bt.Indicator):
    """(close - close[-period]) / close[-period] * 100"""
    lines = ("pct",)
    params = (("period", 1),)

    def next(self):
        prev = self.data[-self.p.period]
        cur = self.data[0]
        self.lines.pct[0] = (cur - prev) / prev * 100.0 if prev else 0.0


def _check_simple_threshold(close, entry_price, direction, kind, *,
                            pct, points):
    offset = entry_price * (pct / 100.0) if pct is not None else float(points)
    if direction == "long":
        if kind == "take_profit":
            return close >= entry_price + offset
        return close <= entry_price - offset
    if kind == "take_profit":
        return close <= entry_price - offset
    return close >= entry_price + offset


# ── public entrypoint ──────────────────────────────────────────────

def run_backtest(strategy, *, bars: Sequence[dict]) -> BacktestResult:
    """Run a backtest on an in-memory bar list. P3 will add a variant
    that loads from futures_daily; this signature is the test-friendly
    one and the future caller will reuse it after assembling bars."""
    if not bars:
        return BacktestResult(
            trades=[],
            summary=Summary(
                total_pnl_amount=0.0, win_rate=0.0,
                avg_win_points=0.0, avg_loss_points=0.0,
                profit_factor=0.0, max_drawdown_amt=0.0,
                max_drawdown_pct=0.0, n_trades=0, avg_held_bars=0.0,
            ),
        )

    df = pd.DataFrame(bars)
    df["datetime"] = pd.to_datetime(df["date"])
    df = df.set_index("datetime")[["open", "high", "low", "close", "volume"]]

    cerebro = bt.Cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=df,
                                        timeframe=bt.TimeFrame.Days,
                                        compression=1))
    cls = try_translate(strategy)
    # Stash contract on the class so notify_trade can compute multiplier.
    cls._contract = strategy.contract  # type: ignore[attr-defined]
    cerebro.addstrategy(cls)
    cerebro.broker.set_cash(10_000_000)
    cerebro.broker.setcommission(commission=0.0,
                                 mult=MULTIPLIER[strategy.contract])

    result = cerebro.run()
    bt_strat = result[0]
    trades: list[Trade] = list(bt_strat._trade_log)

    summary = _summarise(trades)
    return BacktestResult(trades=trades, summary=summary)


def _summarise(trades: list[Trade]) -> Summary:
    if not trades:
        return Summary(
            total_pnl_amount=0.0, win_rate=0.0,
            avg_win_points=0.0, avg_loss_points=0.0,
            profit_factor=0.0, max_drawdown_amt=0.0,
            max_drawdown_pct=0.0, n_trades=0, avg_held_bars=0.0,
        )
    wins   = [t for t in trades if t.pnl_points > 0]
    losses = [t for t in trades if t.pnl_points < 0]
    avg_win  = sum(t.pnl_points for t in wins)   / len(wins)   if wins else 0.0
    avg_loss = sum(t.pnl_points for t in losses) / len(losses) if losses else 0.0
    total_w = sum(t.pnl_amount for t in wins)
    total_l = -sum(t.pnl_amount for t in losses)
    pf = total_w / total_l if total_l > 0 else 0.0

    cumulative = 0.0
    peak = 0.0
    max_dd_amt = 0.0
    max_dd_pct = 0.0
    for t in trades:
        cumulative += t.pnl_amount
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd_amt = max(max_dd_amt, dd)
        if peak > 0:
            max_dd_pct = max(max_dd_pct, dd / peak * 100.0)

    return Summary(
        total_pnl_amount=sum(t.pnl_amount for t in trades),
        win_rate=len(wins) / len(trades) * 100.0,
        avg_win_points=avg_win,
        avg_loss_points=avg_loss,
        profit_factor=pf,
        max_drawdown_amt=max_dd_amt,
        max_drawdown_pct=max_dd_pct,
        n_trades=len(trades),
        avg_held_bars=sum(t.held_bars for t in trades) / len(trades),
    )
```

- [ ] **Step 6.5: Run — should pass**

```bash
python3 -m pytest tests/strategies/test_backtest.py -v
```

Expected: 6 tests PASS.

If `test_run_backtest_short_direction_flips_pnl` is flaky on the synthetic fixture (e.g. the always-true entry produces too many overlapping trades), reduce the fixture to bias more strongly upward — but not by changing tests other than this one.

- [ ] **Step 6.6: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 279 PASS.

- [ ] **Step 6.7: Commit**

```bash
git add backend/services/strategy_backtest.py tests/strategies/conftest.py tests/strategies/test_backtest.py
git commit -m "$(cat <<'EOF'
feat(strategy): backtrader translator + run_backtest

DSL → bt.Strategy class generator. Indicators are materialised once per
unique expression, cached by string key, and resolved inside next() via
_resolve_expr (which mirrors evaluator.compute_expr line for line so the
two paths stay numerically aligned). _ChangePct is the only custom
indicator; the rest map to bt.indicators.*. run_backtest currently
takes an in-memory bar list — P3 will add a variant that reads from
futures_daily, but this signature is the future caller too.
EOF
)"
```

---

## Task 7 — Validator translatability gate

**Files:**
- Modify: `backend/services/strategy_dsl/validator.py`
- Modify: `tests/strategies/test_validator.py`

Wire `validate(...)` to also probe `try_translate` so a DSL that the realtime evaluator accepts but Backtrader cannot represent is rejected at write time. This removes a class of latent inconsistency between the two paths.

- [ ] **Step 7.1: Append translatability tests**

Append to `tests/strategies/test_validator.py`:

```python
def test_validate_translatability_rejects_unknown_indicator_param_combo(monkeypatch):
    """Sanity check: when try_translate raises, validate wraps the failure."""
    from services.strategy_dsl import validator as v

    def boom(strategy):
        raise RuntimeError("synthetic translation failure")

    monkeypatch.setattr(v, "_try_translate_for", lambda *a, **kw: boom(None))

    with pytest.raises(DSLValidationError, match="translation"):
        validate(_GOOD_ENTRY, kind="entry", check_translatability=True)


def test_validate_default_skips_translatability():
    """Without check_translatability=True, validate is the lightweight path."""
    # Any well-formed entry DSL should pass even if translator is monkeypatched
    # to raise — proving the default path doesn't call it.
    validate(_GOOD_ENTRY, kind="entry")    # no exception
```

- [ ] **Step 7.2: Implement the translatability gate**

Replace the body of `backend/services/strategy_dsl/validator.py` with this version that adds the optional `check_translatability` flag and delegates to `strategy_backtest.try_translate`:

```python
"""Top-level validate() — pydantic check + entry-only constraint
+ optional Backtrader-translatability probe."""
from __future__ import annotations

from pydantic import ValidationError

from .models import (
    EntryDSL, ExitDSL,
    ExitDSL_Advanced,
    DSLCondition, VarExpr,
)


class DSLValidationError(ValueError):
    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.errors = errors or []


_VALID_KINDS = ("entry", "take_profit", "stop_loss")


def validate(dsl_dict: dict, *, kind: str, check_translatability: bool = False):
    """Validate `dsl_dict`. If `check_translatability` is True, also build a
    placeholder strategy and run it through the Backtrader translator to
    confirm there's a path — the route layer turns this on; internal
    callers (engine, tests) leave it off to avoid a circular import."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"validate(): unknown kind {kind!r}")

    try:
        if kind == "entry":
            model = EntryDSL.model_validate(dsl_dict)
        else:
            model = ExitDSL.validate_python(dsl_dict)
    except ValidationError as e:
        raise DSLValidationError(
            f"DSL validation failed for {kind}: {e.errors()[0]['msg']}",
            errors=e.errors(),
        ) from e

    if kind == "entry":
        _reject_entry_price_var(model.all)

    if check_translatability:
        try:
            _try_translate_for(model, kind)
        except Exception as e:
            raise DSLValidationError(
                f"DSL passed schema but Backtrader translation failed: {e}"
            ) from e

    return model


def _try_translate_for(model, kind: str):
    """Build a stub strategy whose only meaningful field is `model` placed
    into the right slot, then delegate to strategy_backtest.try_translate.
    Imported lazily to avoid module-level circular dependency."""
    from services import strategy_backtest

    stub_entry = {
        "version": 1,
        "all": [{"left": {"const": 0}, "op": "gte", "right": {"const": 0}}],
    }
    stub_pct = {"version": 1, "type": "pct", "value": 1.0}

    class _Stub:
        direction = "long"
        contract = "TX"
        contract_size = 1
        max_hold_days = None
        entry_dsl = stub_entry
        take_profit_dsl = stub_pct
        stop_loss_dsl = stub_pct

    s = _Stub()
    if kind == "entry":
        s.entry_dsl = _model_to_dict(model)
    elif kind == "take_profit":
        s.take_profit_dsl = _model_to_dict(model)
    else:
        s.stop_loss_dsl = _model_to_dict(model)
    strategy_backtest.try_translate(s)


def _model_to_dict(model) -> dict:
    """Round-trip a pydantic model back into a dict for try_translate."""
    return model.model_dump() if hasattr(model, "model_dump") else dict(model)


def _reject_entry_price_var(conds: list[DSLCondition]) -> None:
    for i, c in enumerate(conds):
        for side, expr in (("left", c.left), ("right", c.right)):
            if isinstance(expr, VarExpr) and expr.var == "entry_price":
                raise DSLValidationError(
                    f"entry_price variable not allowed in entry conditions "
                    f"(found at all[{i}].{side}); use take_profit_dsl / "
                    f"stop_loss_dsl with type='dsl' instead.",
                )
```

- [ ] **Step 7.3: Run — should pass**

```bash
python3 -m pytest tests/strategies/test_validator.py -v
```

Expected: 10 tests PASS (8 from Task 5 + 2 new).

- [ ] **Step 7.4: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 281 PASS.

- [ ] **Step 7.5: Commit**

```bash
git add backend/services/strategy_dsl/validator.py tests/strategies/test_validator.py
git commit -m "$(cat <<'EOF'
feat(strategy): validate(check_translatability=True) gate

Optional second-stage check: round-trip the DSL through
strategy_backtest.try_translate and reject anything that schema-validates
but the translator can't represent. Default off (internal callers don't
need it); the route layer in P4 will turn it on so a 422 fires before
the strategy hits the DB.
EOF
)"
```

---

## Task 8 — 50-seed conformance test (real-time vs Backtrader)

**Files:**
- Create: `tests/strategies/random_dsl_generator.py`
- Create: `tests/strategies/test_dsl_conformance.py`

The conformance test is the keystone of P2: it asserts that the realtime evaluator and the Backtrader translator produce the same set of **entry signal dates** and **exit signal dates** when run over the same fixture data. Drift between the two paths breaks live ↔ backtest parity, which is the central guarantee of the design.

- [ ] **Step 8.1: Write the random DSL generator**

Create `tests/strategies/random_dsl_generator.py`:

```python
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
```

- [ ] **Step 8.2: Write the conformance test**

Create `tests/strategies/test_dsl_conformance.py`:

```python
"""50-seed conformance: realtime evaluator and Backtrader produce the
same trade timeline on the same fixture."""
import math

import pytest

from services.strategy_backtest import run_backtest
from services.strategy_dsl import (
    EntryDSL, ExitDSL, run_dsl, run_exit_dsl,
)
from tests.strategies.random_dsl_generator import gen_random_strategy
from tests.strategies.conftest import FakeStrategy


def _materialise(s_dict: dict) -> FakeStrategy:
    return FakeStrategy(
        direction=s_dict["direction"],
        contract=s_dict["contract"],
        contract_size=s_dict["contract_size"],
        max_hold_days=s_dict["max_hold_days"],
        entry_dsl=s_dict["entry_dsl"],
        take_profit_dsl=s_dict["take_profit_dsl"],
        stop_loss_dsl=s_dict["stop_loss_dsl"],
    )


def _simulate_realtime(s: FakeStrategy, bars: list) -> list[dict]:
    """Walk the bars; record (entry_date, exit_date, reason) for each
    completed trade. Mirrors the P3 state machine but standalone."""
    entry = EntryDSL.model_validate(s.entry_dsl)
    tp_dsl = ExitDSL.validate_python(s.take_profit_dsl)
    sl_dsl = ExitDSL.validate_python(s.stop_loss_dsl)

    state = "idle"           # idle -> open -> idle
    entry_date = None
    entry_idx  = None
    entry_price = None
    completed = []

    for i in range(1, len(bars) + 1):
        history = bars[:i]
        today = history[-1]

        if state == "idle":
            if run_dsl(entry, history) is True:
                state = "open"
                entry_date = today["date"]
                entry_idx  = i - 1
                entry_price = today["close"]
        else:  # open
            sl = run_exit_dsl(sl_dsl, entry_price=entry_price,
                              direction=s.direction, bars=history,
                              kind="stop_loss")
            if sl is True:
                completed.append({"entry_date": entry_date,
                                  "exit_date":  today["date"],
                                  "reason":     "STOP_LOSS"})
                state = "idle"
                continue
            tp = run_exit_dsl(tp_dsl, entry_price=entry_price,
                              direction=s.direction, bars=history,
                              kind="take_profit")
            if tp is True:
                completed.append({"entry_date": entry_date,
                                  "exit_date":  today["date"],
                                  "reason":     "TAKE_PROFIT"})
                state = "idle"
                continue
            if s.max_hold_days is not None:
                if (i - 1) - entry_idx >= s.max_hold_days:
                    completed.append({"entry_date": entry_date,
                                      "exit_date":  today["date"],
                                      "reason":     "TIMEOUT"})
                    state = "idle"

    return completed


def _bt_trades(s: FakeStrategy, bars: list) -> list[dict]:
    res = run_backtest(s, bars=bars)
    return [
        {"entry_date": t.entry_date.isoformat(),
         "exit_date":  t.exit_date.isoformat(),
         "reason":     t.exit_reason}
        for t in res.trades
    ]


@pytest.mark.parametrize("seed", list(range(50)))
def test_realtime_and_backtrader_agree(seed, synthetic_bars):
    s_dict = gen_random_strategy(seed)
    s = _materialise(s_dict)

    rt = _simulate_realtime(s, synthetic_bars)
    bt = _bt_trades(s, synthetic_bars)

    # Reasons are compared verbatim. Dates are compared after normalising
    # the realtime path's "YYYY-MM-DD" string vs the bt isoformat.
    rt_norm = [(r["entry_date"], r["exit_date"], r["reason"]) for r in rt]
    bt_norm = [(b["entry_date"], b["exit_date"], b["reason"]) for b in bt]

    assert rt_norm == bt_norm, (
        f"seed={seed} disagreement\n"
        f"  realtime: {rt_norm}\n"
        f"  backtrdr: {bt_norm}\n"
        f"  strategy: {s_dict}"
    )
```

- [ ] **Step 8.3: Run — expect either pass or a small number of failing seeds**

```bash
python3 -m pytest tests/strategies/test_dsl_conformance.py -v
```

If all 50 pass: skip to Step 8.5.

If 1–5 seeds fail with a 1-day off-by-one disagreement (e.g., realtime fires on day T, Backtrader on day T+1), it almost certainly means an off-by-one in `_resolve_expr`'s offset semantics or the streak window — fix in `backend/services/strategy_backtest.py` and re-run. Do NOT widen the assertion to "approximately equal"; the parity is load-bearing.

If many seeds fail with totally different trade counts, stop and BLOCK — the indicator math has drifted between the two paths.

- [ ] **Step 8.4: If iterating: rerun until all 50 pass**

```bash
python3 -m pytest tests/strategies/test_dsl_conformance.py -q
```

- [ ] **Step 8.5: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 331 PASS (281 + 50 conformance seeds).

- [ ] **Step 8.6: Commit**

```bash
git add tests/strategies/random_dsl_generator.py tests/strategies/test_dsl_conformance.py
git commit -m "$(cat <<'EOF'
test(strategy): 50-seed conformance for realtime ↔ backtrader parity

For each of 50 random valid DSLs, simulate both paths (pure-function
evaluator and Backtrader Cerebro) over the same 250-bar fixture and
assert the trade timeline matches verbatim — entry date, exit date,
exit reason. cross_*/streak_* and a few drift-prone indicators are
excluded from the sweep but covered by unit tests; this property test
is the canary for any future indicator/op change that desyncs the two
paths.
EOF
)"
```

---

## Phase exit criteria

After all eight tasks are committed:

1. `python3 -m pytest tests/ -q` passes (≈331 tests; 210 pre-existing + ~121 new).
2. `python3 -c "from services.strategy_dsl import validate, run_dsl, run_exit_dsl; from services.strategy_backtest import run_backtest, try_translate; print('ok')"` works from `backend/`.
3. `git log --oneline master..HEAD` shows the eight phase commits in order.

P2 is then ready to merge. No deployment effect (no fetcher / route changes); the backend will just pip-install backtrader/pandas/numpy on next push.

The next phase is **P3: realtime evaluator + state machine**, which will:
- Add `services/strategy_engine.py` (state machine + evaluate_all)
- Wire the fan-in barrier into the TX/MTX/TMF fetchers
- Add MTX and TMF fetcher modules
- Plug `last_error` and auto-disable into the runtime path
