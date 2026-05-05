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
