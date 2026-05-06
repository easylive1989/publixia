"""Pydantic request/response models for /api/strategies/* routes.

The DSL bodies (entry_dsl, take_profit_dsl, stop_loss_dsl) are kept as
permissive `dict` here — services.strategy_dsl.validator does the
exact-shape check at write time and raises a precise 422.
"""
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyCreate(_Strict):
    name:            str = Field(min_length=1, max_length=80)
    direction:       Literal["long", "short"]
    contract:        Literal["TX", "MTX", "TMF"]
    contract_size:   int = Field(ge=1, le=1000)
    max_hold_days:   int | None = Field(default=None, ge=1, le=10_000)
    entry_dsl:       dict
    take_profit_dsl: dict
    stop_loss_dsl:   dict


class StrategyUpdate(_Strict):
    """All fields optional; only present keys are written."""
    name:            str | None = Field(default=None, min_length=1, max_length=80)
    direction:       Literal["long", "short"] | None = None
    contract:        Literal["TX", "MTX", "TMF"] | None = None
    contract_size:   int | None = Field(default=None, ge=1, le=1000)
    max_hold_days:   int | None = Field(default=None, ge=1, le=10_000)
    entry_dsl:       dict | None = None
    take_profit_dsl: dict | None = None
    stop_loss_dsl:   dict | None = None


class StrategyResponse(_Strict):
    """Full strategy row including state machine + last_error."""
    id:                       int
    user_id:                  int
    name:                     str
    direction:                str
    contract:                 str
    contract_size:            int
    max_hold_days:            int | None
    entry_dsl:                dict
    take_profit_dsl:          dict
    stop_loss_dsl:            dict
    notify_enabled:           bool
    state:                    str
    entry_signal_date:        str | None
    entry_fill_date:          str | None
    entry_fill_price:         float | None
    pending_exit_kind:        str | None
    pending_exit_signal_date: str | None
    last_error:               str | None
    last_error_at:            str | None
    created_at:               str
    updated_at:               str


class SignalResponse(_Strict):
    id:              int
    strategy_id:     int
    kind:            str
    signal_date:     str
    close_at_signal: float | None
    fill_price:      float | None
    exit_reason:     str | None
    pnl_points:      float | None
    pnl_amount:      float | None
    message:         str | None
    created_at:      str


class BacktestRequest(_Strict):
    start_date:    Date
    end_date:      Date
    contract:      Literal["TX", "MTX", "TMF"] | None = None
    contract_size: int | None = Field(default=None, ge=1, le=1000)


class TradeOut(_Strict):
    entry_date:  str
    entry_price: float
    exit_date:   str
    exit_price:  float
    exit_reason: str
    held_bars:   int
    pnl_points:  float
    pnl_amount:  float
    from_stop:   bool


class SummaryOut(_Strict):
    total_pnl_amount: float
    win_rate:         float
    avg_win_points:   float
    avg_loss_points:  float
    profit_factor:    float
    max_drawdown_amt: float
    max_drawdown_pct: float
    n_trades:         int
    avg_held_bars:    float


class BacktestResponse(_Strict):
    trades:   list[TradeOut]
    summary:  SummaryOut
    warnings: list[str]
