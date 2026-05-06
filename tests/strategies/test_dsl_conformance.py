"""50-seed conformance: realtime evaluator and Backtrader produce the
same trade timeline on the same fixture.

We compare CLOSED trades — i.e., entries that have a clear take-profit /
stop-loss / true-timeout exit during the run. End-of-data
auto-flushed positions (which Backtrader's stop() hook synthesises so
the backtest UI can show open PnL) are filtered out before comparison.

**Order-fill semantics** (why _simulate_realtime uses a pending-order
state machine instead of a simple loop):

Backtrader executes Market orders on the NEXT bar after the signal fires.
The entry date recorded in the trade is the fill bar (signal_bar + 1).
The exit date is likewise the bar after the exit condition triggers.
And the timeout held-days counter is measured from the SIGNAL bar (not
the fill bar), matching BT's ``held = len(self) - _entry_bar_idx`` where
``_entry_bar_idx`` is set at signal time.

The pending-order machine below mirrors this exactly:
  - state ``idle``         → check entry signal; if True go ``waiting_entry``
  - state ``waiting_entry`` → fill entry on this bar (don't advance i);
                              transition to ``open``
  - state ``open``         → check exits; if triggered go ``waiting_exit``
  - state ``waiting_exit`` → record trade with exit_date=today; go ``idle``
                              (don't advance i so new signal can fire same bar)
"""
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
    """Walk the bars with BT-equivalent Market-order fill semantics.

    Signal fires at bar N; fill (and trade record) happen at bar N+1.
    Timeout held-days count starts from the signal bar, not the fill bar,
    matching Backtrader's ``held = len(self) - _entry_bar_idx``.
    Open-at-end positions are NOT logged (matches live runtime semantics).
    """
    entry_dsl = EntryDSL.model_validate(s.entry_dsl)
    tp_dsl    = ExitDSL.validate_python(s.take_profit_dsl)
    sl_dsl    = ExitDSL.validate_python(s.stop_loss_dsl)

    # state machine: idle → waiting_entry → open → waiting_exit → idle
    state         = "idle"
    signal_bar    = None   # 0-indexed bar index where entry signal fired
    entry_date    = None
    entry_price   = None
    pending_reason = None
    completed: list[dict] = []

    i = 0
    n = len(bars)
    while i < n:
        today   = bars[i]
        history = bars[: i + 1]

        if state == "idle":
            if run_dsl(entry_dsl, history) is True:
                signal_bar = i   # same semantics as BT's _entry_bar_idx = len(self)
                state = "waiting_entry"
            i += 1

        elif state == "waiting_entry":
            # Fill at this bar (next bar after signal)
            entry_date  = today["date"]
            entry_price = today["open"]   # Market fill = open of next bar
            state = "open"
            # Do NOT advance i — check exits on this same bar

        elif state == "open":
            sl = run_exit_dsl(sl_dsl, entry_price=entry_price,
                              direction=s.direction, bars=history,
                              kind="stop_loss")
            if sl is True:
                state = "waiting_exit"
                pending_reason = "STOP_LOSS"
                i += 1
                continue
            tp = run_exit_dsl(tp_dsl, entry_price=entry_price,
                              direction=s.direction, bars=history,
                              kind="take_profit")
            if tp is True:
                state = "waiting_exit"
                pending_reason = "TAKE_PROFIT"
                i += 1
                continue
            if s.max_hold_days is not None:
                # BT: held = len(self) [current bar] - _entry_bar_idx [signal bar]
                # In 0-indexed terms: held = i - signal_bar
                held = i - signal_bar
                if held >= s.max_hold_days:
                    state = "waiting_exit"
                    pending_reason = "TIMEOUT"
                    i += 1
                    continue
            i += 1

        elif state == "waiting_exit":
            # Exit fills at this bar
            completed.append({"entry_date": entry_date,
                               "exit_date":  today["date"],
                               "reason":     pending_reason})
            state = "idle"
            signal_bar    = None
            entry_date    = None
            entry_price   = None
            pending_reason = None
            # Do NOT advance i — new entry signal can fire on this same bar

    return completed


def _bt_closed_trades(s: FakeStrategy, bars: list) -> list[dict]:
    """Run Backtrader and filter to closed trades only.

    Excludes trades synthesised by the stop() hook (open positions still
    held when bars run out). These are tagged with Trade.from_stop=True
    in strategy_backtest.py and represent the open-PnL UX feature, not
    a completed trade that the realtime simulator would have recorded.
    """
    res = run_backtest(s, bars=bars)
    out = []
    for t in res.trades:
        if t.from_stop:
            continue   # end-of-data auto-flush — not a true exit
        out.append({"entry_date": t.entry_date.isoformat(),
                    "exit_date":  t.exit_date.isoformat(),
                    "reason":     t.exit_reason})
    return out


@pytest.mark.parametrize("seed", list(range(50)))
def test_realtime_and_backtrader_agree(seed, synthetic_bars):
    s_dict = gen_random_strategy(seed)
    s = _materialise(s_dict)

    rt = _simulate_realtime(s, synthetic_bars)
    bt = _bt_closed_trades(s, synthetic_bars)

    rt_norm = [(r["entry_date"], r["exit_date"], r["reason"]) for r in rt]
    bt_norm = [(b["entry_date"], b["exit_date"], b["reason"]) for b in bt]

    assert rt_norm == bt_norm, (
        f"seed={seed} disagreement\n"
        f"  realtime: {rt_norm}\n"
        f"  backtrdr: {bt_norm}\n"
        f"  strategy: {s_dict}"
    )
