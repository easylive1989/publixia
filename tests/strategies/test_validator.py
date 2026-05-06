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


def test_validate_translatability_rejects_unknown_indicator_param_combo(monkeypatch):
    """Sanity check: when try_translate raises, validate wraps the failure."""
    from services.strategy_dsl import validator as v

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic translation failure")

    monkeypatch.setattr(v, "_try_translate_for", boom)

    with pytest.raises(DSLValidationError, match="translation"):
        validate(_GOOD_ENTRY, kind="entry", check_translatability=True)


def test_validate_default_skips_translatability(monkeypatch):
    """Without check_translatability=True, validate is the lightweight path —
    proven by monkeypatching _try_translate_for to fail and showing it's
    never reached."""
    from services.strategy_dsl import validator as v

    def boom(*args, **kwargs):
        raise RuntimeError("should not be called")

    monkeypatch.setattr(v, "_try_translate_for", boom)
    # Should not raise — translatability check skipped by default.
    validate(_GOOD_ENTRY, kind="entry")
