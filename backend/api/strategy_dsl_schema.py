"""Static metadata for GET /api/strategies/dsl/schema.

This is what the P5 frontend's condition builder reads to enumerate the
fields, operators, and indicators it should render. The values mirror
backend/services/strategy_dsl/models.py's runtime schema; the route
serialises this dict directly. Tests assert that every indicator listed
here is also accepted by the runtime models, preventing drift.
"""
from typing import Final


DSL_SCHEMA: Final[dict] = {
    "version": 1,
    "fields":     ["open", "high", "low", "close", "volume"],
    "operators":  [
        "gt", "gte", "lt", "lte",
        "cross_above", "cross_below",
        "streak_above", "streak_below",
    ],
    "indicators": [
        {"name": "sma",        "params": [{"name": "n", "type": "int", "min": 1}]},
        {"name": "ema",        "params": [{"name": "n", "type": "int", "min": 1}]},
        {"name": "rsi",        "params": [{"name": "n", "type": "int", "min": 2, "default": 14}]},
        {"name": "macd",       "params": [
            {"name": "fast",   "type": "int", "min": 1, "default": 12},
            {"name": "slow",   "type": "int", "min": 2, "default": 26},
            {"name": "signal", "type": "int", "min": 1, "default": 9},
            {"name": "output", "type": "enum", "choices": ["macd", "signal", "hist"], "default": "macd"},
        ]},
        {"name": "bbands",     "params": [
            {"name": "n",      "type": "int",   "min": 2,  "default": 20},
            {"name": "k",      "type": "float", "min": 0,  "default": 2.0},
            {"name": "output", "type": "enum",  "choices": ["upper", "middle", "lower"], "default": "middle"},
        ]},
        {"name": "atr",        "params": [{"name": "n", "type": "int", "min": 1, "default": 14}]},
        {"name": "kd",         "params": [
            {"name": "n",      "type": "int",  "min": 1, "default": 9},
            {"name": "output", "type": "enum", "choices": ["k", "d"], "default": "k"},
        ]},
        {"name": "highest",    "params": [{"name": "n", "type": "int", "min": 1}]},
        {"name": "lowest",     "params": [{"name": "n", "type": "int", "min": 1}]},
        {"name": "change_pct", "params": [{"name": "n", "type": "int", "min": 1}]},
    ],
    "exit_modes": ["pct", "points", "dsl"],
    "vars":       ["entry_price"],
}
