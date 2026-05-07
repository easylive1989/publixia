"""Strategy state machine — daily evaluation against new futures bars.

Lifecycle (per spec §3.5):

    idle → pending_entry → open → pending_exit → idle
        ↑         ↑          ↑         ↑
        │         │          │         │
        T         T+1        E         E+1

The state machine is faithful to the P2 conformance test's
_simulate_realtime (tests/strategies/test_dsl_conformance.py).

Critical invariants:

1. `entry_signal_date` is the bar where the signal fired (T). The
   `entry_fill_date` is T+1, and `entry_fill_price` = T+1's open.
   Held-days for max_hold is measured from `entry_signal_date` so
   it matches Backtrader's `len(self) - _entry_bar_idx` where
   `_entry_bar_idx` is set at signal time.

2. A single evaluate_one call may chain transitions on the same bar:
   - pending_entry on T+1: fill → open → optionally try_exit on T+1.
   - pending_exit on E+1: fill → idle → optionally try_entry on E+1.

3. Any exception inside handlers is caught at the top, the strategy
   is auto-disabled (notify_enabled=0, last_error set), and
   notify_runtime_error fires. Other strategies on the same contract
   are unaffected.

P3 only writes signal rows + advances state. The notifier stub merely
logs; P4 swaps in real Discord embeds.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from core.contracts import MULTIPLIER
from repositories.futures import get_futures_daily_range, get_latest_futures_bar
from repositories.strategies import (
    list_enabled_strategies, get_strategy,
    update_strategy_state, write_signal, mark_strategy_error,
)
from services.strategy_dsl import (
    EntryDSL, ExitDSL, run_dsl, run_exit_dsl, required_lookback,
)
from services.strategy_notifier import notify_signal, notify_runtime_error

logger = logging.getLogger(__name__)


# ── public API ─────────────────────────────────────────────────────

def evaluate_one(strategy: dict, today_bar: dict) -> None:
    """Advance one strategy by one bar. Mutates DB; never raises."""
    sid = strategy["id"]
    try:
        s = strategy

        # Phase 1 — fill any pending fill state.
        if s["state"] == "pending_entry":
            _fill_entry(s, today_bar)
            s = get_strategy(sid)
            if s is None:
                return
        elif s["state"] == "pending_exit":
            _fill_exit(s, today_bar)
            s = get_strategy(sid)
            if s is None:
                return

        # Phase 2 — state is now idle or open; check signals on today.
        if s["state"] == "open":
            _try_exit(s, today_bar)
        elif s["state"] == "idle":
            _try_entry(s, today_bar)

    except Exception as e:
        logger.exception("strategy_evaluate_failed id=%s", sid)
        mark_strategy_error(sid, str(e))
        notify_runtime_error(strategy, e)


def evaluate_all(date: str) -> None:
    """For each contract, evaluate every enabled strategy. Used by tests
    and a future admin "re-evaluate today" command."""
    for contract in ("TX", "MTX", "TMF"):
        on_futures_data_written(contract, date)


def on_futures_data_written(contract: str, date: str) -> None:
    """Fetcher tail-call entrypoint. Looks up today's bar, then advances
    every enabled strategy on this contract by one step."""
    today_bar = _fetch_today_bar(contract, date)
    if today_bar is None:
        logger.warning("strategy_engine_no_bar contract=%s date=%s",
                       contract, date)
        return
    for s in list_enabled_strategies(contract=contract):
        evaluate_one(s, today_bar)


# ── handlers ────────────────────────────────────────────────────────

def _try_entry(strategy: dict, today_bar: dict) -> None:
    # Validate bar shape early — dereference "close" so that a malformed
    # bar raises KeyError before we touch the DB, which lets the top-level
    # try/except in evaluate_one mark the strategy as errored.
    close_at_signal = today_bar["close"]
    entry = EntryDSL.model_validate(strategy["entry_dsl"])
    history = _history_for(strategy, today_bar, entry.all)
    fired = run_dsl(entry, history)
    if fired is not True:        # False or None — not firing
        return
    write_signal(
        strategy["id"], kind="ENTRY_SIGNAL",
        signal_date=today_bar["date"],
        close_at_signal=close_at_signal,
    )
    update_strategy_state(
        strategy["id"],
        state="pending_entry",
        entry_signal_date=today_bar["date"],
    )
    notify_signal(strategy, "ENTRY_SIGNAL", today_bar)


def _fill_entry(strategy: dict, today_bar: dict) -> None:
    write_signal(
        strategy["id"], kind="ENTRY_FILLED",
        signal_date=today_bar["date"],
        fill_price=today_bar["open"],
    )
    update_strategy_state(
        strategy["id"],
        state="open",
        entry_fill_date=today_bar["date"],
        entry_fill_price=today_bar["open"],
    )


def _try_exit(strategy: dict, today_bar: dict) -> None:
    sl_dsl = ExitDSL.validate_python(strategy["stop_loss_dsl"])
    tp_dsl = ExitDSL.validate_python(strategy["take_profit_dsl"])
    history = _history_for_exit(strategy, today_bar, sl_dsl, tp_dsl)
    entry_price = strategy["entry_fill_price"]
    direction = strategy["direction"]

    sl = run_exit_dsl(sl_dsl, entry_price=entry_price, direction=direction,
                      bars=history, kind="stop_loss")
    if sl is True:
        return _emit_exit_signal(strategy, today_bar, "STOP_LOSS")

    tp = run_exit_dsl(tp_dsl, entry_price=entry_price, direction=direction,
                      bars=history, kind="take_profit")
    if tp is True:
        return _emit_exit_signal(strategy, today_bar, "TAKE_PROFIT")

    if strategy["max_hold_days"] is not None:
        held = _trading_days_between(
            strategy["contract"],
            strategy["entry_signal_date"], today_bar["date"],
        )
        if held >= strategy["max_hold_days"]:
            return _emit_exit_signal(strategy, today_bar, "TIMEOUT")


def _emit_exit_signal(strategy: dict, today_bar: dict, exit_reason: str) -> None:
    write_signal(
        strategy["id"], kind="EXIT_SIGNAL",
        signal_date=today_bar["date"],
        close_at_signal=today_bar["close"],
        exit_reason=exit_reason,
    )
    update_strategy_state(
        strategy["id"],
        state="pending_exit",
        pending_exit_kind=exit_reason,
        pending_exit_signal_date=today_bar["date"],
    )
    # Inject the just-decided reason into the local dict so the notifier
    # renders the right title/colour. Without this, strategy["pending_exit_kind"]
    # is still None and every real exit would post as "🔧 手動平倉".
    strategy = {**strategy, "pending_exit_kind": exit_reason}
    notify_signal(strategy, "EXIT_SIGNAL", today_bar)


def _fill_exit(strategy: dict, today_bar: dict) -> None:
    fill = today_bar["open"]
    entry_price = strategy["entry_fill_price"]
    direction = strategy["direction"]
    if direction == "long":
        pnl_points = fill - entry_price
    else:
        pnl_points = entry_price - fill
    pnl_amount = (
        pnl_points
        * MULTIPLIER[strategy["contract"]]
        * strategy["contract_size"]
    )

    write_signal(
        strategy["id"], kind="EXIT_FILLED",
        signal_date=today_bar["date"],
        fill_price=fill,
        exit_reason=strategy["pending_exit_kind"],
        pnl_points=pnl_points,
        pnl_amount=pnl_amount,
    )
    update_strategy_state(
        strategy["id"],
        state="idle",
        entry_signal_date=None,
        entry_fill_date=None,
        entry_fill_price=None,
        pending_exit_kind=None,
        pending_exit_signal_date=None,
    )


# ── helpers ─────────────────────────────────────────────────────────

def _fetch_today_bar(contract: str, date: str) -> Optional[dict]:
    """Find the bar for `date` in futures_daily — None if the fetcher
    didn't actually persist it (failure path or weekend)."""
    rows = get_futures_daily_range(contract, date)
    for r in rows:
        if r["date"] == date:
            return r
    return None


def _history_for(strategy: dict, today_bar: dict, conds) -> list[dict]:
    """Bars window large enough to evaluate every condition's expressions.

    Returns an empty list when the DSL requires zero bar history (e.g. a
    DSL composed entirely of const/var expressions). run_dsl treats an
    empty bars argument as "insufficient history → None", which prevents
    const-only conditions from spuriously firing in the engine without
    real bar data being present.
    """
    n_required = max(
        (max(required_lookback(c.left), required_lookback(c.right)) for c in conds),
        default=1,
    )
    if n_required == 0:
        return []
    return _fetch_history(strategy["contract"], today_bar["date"], n_required)


def _history_for_exit(strategy: dict, today_bar: dict,
                      sl_dsl, tp_dsl) -> list[dict]:
    n_required = 1
    for dsl in (sl_dsl, tp_dsl):
        if hasattr(dsl, "all"):
            for c in dsl.all:
                n_required = max(
                    n_required,
                    required_lookback(c.left),
                    required_lookback(c.right),
                )
    return _fetch_history(strategy["contract"], today_bar["date"], n_required)


def _fetch_history(contract: str, today_date: str, n_bars: int) -> list[dict]:
    """Pull ≥ n_bars trading days ending on today_date inclusive.

    Over-reads by 2x + 30 calendar days to cover weekends and holidays
    cheaply; SQL ORDER BY date keeps it deterministic."""
    today_obj = datetime.strptime(today_date, "%Y-%m-%d").date()
    since = (today_obj - timedelta(days=n_bars * 2 + 30)).strftime("%Y-%m-%d")
    rows = get_futures_daily_range(contract, since)
    return [r for r in rows if r["date"] <= today_date]


def _trading_days_between(contract: str, signal_date: str,
                          today_date: str) -> int:
    """Count trading-day rows strictly after signal_date, up to and
    including today_date."""
    rows = get_futures_daily_range(contract, signal_date)
    return len([r for r in rows
                if signal_date < r["date"] <= today_date])


def required_history_for_strategy(strategy: dict) -> int:
    """Compute the minimum bar count the engine needs to evaluate an
    entry signal for this strategy. Used by the API enable handler.

    For all-const DSLs the count is 1 — the engine still needs at least
    one bar to even talk about close/today. For indicator-bearing DSLs
    we take the maximum lookback across the entry conditions.
    """
    entry = EntryDSL.model_validate(strategy["entry_dsl"])
    n = 1
    for cond in entry.all:
        n = max(
            n,
            required_lookback(cond.left),
            required_lookback(cond.right),
        )
    return n


def force_close(strategy: dict) -> None:
    """Manually close a hypothetical position outside the daily cycle.

    Permitted only when state ∈ {open, pending_exit}. Uses the most
    recent bar's close as the assumed fill price (next-bar open isn't
    available — the user is acting ad-hoc, not reacting to a fresh
    fetch). Writes a single EXIT_FILLED row with exit_reason='MANUAL_RESET'
    and resets state to idle.
    """
    if strategy["state"] not in ("open", "pending_exit"):
        raise ValueError(
            f"strategy {strategy['id']} not in position "
            f"(state={strategy['state']!r}); use /reset for pending_entry"
        )
    last_bar = get_latest_futures_bar(strategy["contract"])
    if last_bar is None:
        raise ValueError(
            f"no bars in futures_daily for contract={strategy['contract']!r}"
        )
    fill = float(last_bar["close"])
    entry_price = strategy["entry_fill_price"] or 0.0
    direction = strategy["direction"]
    if direction == "long":
        pnl_points = fill - entry_price
    else:
        pnl_points = entry_price - fill
    pnl_amount = (
        pnl_points
        * MULTIPLIER[strategy["contract"]]
        * strategy["contract_size"]
    )
    write_signal(
        strategy["id"], kind="EXIT_FILLED",
        signal_date=last_bar["date"],
        fill_price=fill,
        exit_reason="MANUAL_RESET",
        pnl_points=pnl_points,
        pnl_amount=pnl_amount,
    )
    update_strategy_state(
        strategy["id"],
        state="idle",
        entry_signal_date=None, entry_fill_date=None,
        entry_fill_price=None,
        pending_exit_kind=None, pending_exit_signal_date=None,
    )
    # Tag the in-memory dict so the notifier renders "🔧 手動平倉"
    # regardless of what kind was pending before force_close ran.
    strategy = {**strategy, "pending_exit_kind": "MANUAL_RESET"}
    notify_signal(strategy, "EXIT_FILLED", last_bar)
