"""Shared contract metadata for Taiwan futures.

Multiplier in NTD per index point. Used by:
  - services.strategy_backtest (cerebro PnL accounting)
  - services.strategy_engine (P3, live PnL when emitting EXIT_FILLED signals)
  - services.strategy_notifier (P4, Discord embed PnL formatting)

Keeping this in one place avoids drift if the exchange ever changes a
multiplier (TX has been 200 since launch; MTX/TMF less so).
"""
from typing import Final, Mapping


MULTIPLIER: Final[Mapping[str, int]] = {
    "TX":  200,   # 大台
    "MTX": 50,    # 小台
    "TMF": 10,    # 微台
}
