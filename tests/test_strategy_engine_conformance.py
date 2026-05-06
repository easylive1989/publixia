"""50-seed conformance: production state machine matches the P2 reference.

For each random valid DSL:
  1. Insert it as a `strategies` row.
  2. Walk the synthetic 250-bar fixture; for each bar, call
     services.strategy_engine.evaluate_one with the strategy's current
     row + that bar.
  3. After the walk, read EXIT_FILLED rows from strategy_signals; pair
     each with its preceding ENTRY_FILLED to reconstruct trades.
  4. Compare to the P2 reference (`_simulate_realtime`) for the same
     strategy + same fixture.

If the lists match for all 50 seeds, P3 has carried the contract.
"""
import json

import pytest

from db.connection import get_connection
from repositories.futures import save_futures_daily_rows
from repositories.strategies import get_strategy, list_signals
from services.strategy_engine import evaluate_one
from tests.strategies.conftest import FakeStrategy
from tests.strategies.random_dsl_generator import gen_random_strategy
from tests.strategies.test_dsl_conformance import _simulate_realtime


def _seed_bars(symbol: str, bars: list[dict]) -> None:
    rows = [{
        "symbol": symbol, "date": b["date"],
        "contract_date": "202607",
        "open":          b["open"],   "high":   b["high"],
        "low":           b["low"],    "close":  b["close"],
        "volume":        b.get("volume", 1000),
        "open_interest": None, "settlement": None,
    } for b in bars]
    save_futures_daily_rows(rows)


def _insert_strategy_from_dict(s_dict: dict) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO strategies "
            "(user_id, name, direction, contract, contract_size, "
            " max_hold_days, entry_dsl, take_profit_dsl, stop_loss_dsl, "
            " notify_enabled, state, created_at, updated_at) "
            "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'idle', "
            " '2026-01-01T00:00:00', '2026-01-01T00:00:00')",
            (f"conformance_{id(s_dict)}", s_dict["direction"],
             s_dict["contract"], s_dict["contract_size"],
             s_dict["max_hold_days"],
             json.dumps(s_dict["entry_dsl"]),
             json.dumps(s_dict["take_profit_dsl"]),
             json.dumps(s_dict["stop_loss_dsl"])),
        )
        conn.commit()
        return cur.lastrowid


def _walk_engine(strategy_id: int, bars: list[dict]) -> list[dict]:
    """For each bar, call evaluate_one and return the resulting closed-
    trade list (entry_date, exit_date, exit_reason)."""
    for bar in bars:
        s = get_strategy(strategy_id)
        if s is None or not s["notify_enabled"]:
            break
        evaluate_one(s, bar)

    # The engine must NOT have errored mid-walk — that would silently
    # truncate the trade list and a downstream `eng == ref` mismatch
    # would look like a state-machine bug instead of a runtime crash.
    final = get_strategy(strategy_id)
    assert final is not None, f"strategy {strategy_id} disappeared mid-walk"
    assert final["last_error"] is None, (
        f"strategy {strategy_id} errored mid-walk: {final['last_error']}"
    )

    # Reconstruct trades from EXIT_FILLED + matching ENTRY_FILLED.
    # Invariant: signal kinds (filtered to FILLED) must alternate
    # ENTRY_FILLED, EXIT_FILLED, ENTRY_FILLED, ...
    sigs = list_signals(strategy_id, limit=10_000)
    sigs.reverse()  # oldest first
    fill_kinds = [s["kind"] for s in sigs
                  if s["kind"] in ("ENTRY_FILLED", "EXIT_FILLED")]
    expected = ["ENTRY_FILLED", "EXIT_FILLED"] * (len(fill_kinds) // 2 + 1)
    assert fill_kinds == expected[:len(fill_kinds)], (
        f"non-alternating fill kinds: {fill_kinds}"
    )

    trades: list[dict] = []
    pending_entry_date: str | None = None
    for s in sigs:
        if s["kind"] == "ENTRY_FILLED":
            pending_entry_date = s["signal_date"]
        elif s["kind"] == "EXIT_FILLED" and pending_entry_date:
            trades.append({
                "entry_date": pending_entry_date,
                "exit_date":  s["signal_date"],
                "reason":     s["exit_reason"],
            })
            pending_entry_date = None
    return trades


@pytest.mark.parametrize("seed", list(range(50)))
def test_engine_matches_p2_reference(seed, synthetic_bars):
    s_dict = gen_random_strategy(seed)
    sid = _insert_strategy_from_dict(s_dict)
    _seed_bars(s_dict["contract"], synthetic_bars)

    engine_trades = _walk_engine(sid, synthetic_bars)

    fake = FakeStrategy(
        direction=s_dict["direction"],
        contract=s_dict["contract"],
        contract_size=s_dict["contract_size"],
        max_hold_days=s_dict["max_hold_days"],
        entry_dsl=s_dict["entry_dsl"],
        take_profit_dsl=s_dict["take_profit_dsl"],
        stop_loss_dsl=s_dict["stop_loss_dsl"],
    )
    reference = _simulate_realtime(fake, synthetic_bars)

    eng = [(t["entry_date"], t["exit_date"], t["reason"]) for t in engine_trades]
    ref = [(r["entry_date"], r["exit_date"], r["reason"]) for r in reference]

    assert eng == ref, (
        f"seed={seed} engine ↔ reference mismatch\n"
        f"  engine:    {eng}\n"
        f"  reference: {ref}\n"
        f"  strategy:  {s_dict}"
    )
