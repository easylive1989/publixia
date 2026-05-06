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
