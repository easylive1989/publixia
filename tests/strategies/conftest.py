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
    (sin + drift); H/L are mid ± 5; volume is constant.

    Dates are sequential calendar days from 2026-01-01 so every date string
    is a valid ISO-8601 date that pandas can parse without ambiguity."""
    import datetime
    base = datetime.date(2026, 1, 1)
    bars = []
    for i in range(250):
        mid = 100.0 + 0.05 * i + 5.0 * math.sin(i / 7.0)
        bars.append({
            "date":   str(base + datetime.timedelta(days=i)),
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
