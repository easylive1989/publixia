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
