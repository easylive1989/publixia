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
