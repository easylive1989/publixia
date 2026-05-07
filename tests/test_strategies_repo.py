"""Tests for repositories.strategies — CRUD + signal log + JSON marshalling."""
import json

import pytest

from db.connection import get_connection
from repositories.strategies import (
    list_enabled_strategies, get_strategy,
    update_strategy_state, write_signal, list_signals,
    mark_strategy_error,
)


_GOOD_ENTRY_DSL = {
    "version": 1,
    "all": [{"left": {"field": "close"}, "op": "gt",
             "right": {"const": 100}}],
}
_GOOD_PCT_DSL = {"version": 1, "type": "pct", "value": 2.0}


def _insert_strategy(*, name="s1", user_id=1, notify_enabled=True,
                     contract="TX", direction="long",
                     state="idle") -> int:
    """Helper that bypasses the (P4) repo writer and INSERTs directly."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO strategies "
            "(user_id, name, direction, contract, contract_size, "
            " entry_dsl, take_profit_dsl, stop_loss_dsl, "
            " notify_enabled, state, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, "
            " '2026-01-01T00:00:00', '2026-01-01T00:00:00')",
            (user_id, name, direction, contract,
             json.dumps(_GOOD_ENTRY_DSL),
             json.dumps(_GOOD_PCT_DSL),
             json.dumps(_GOOD_PCT_DSL),
             1 if notify_enabled else 0, state),
        )
        conn.commit()
        return cur.lastrowid


def test_get_strategy_returns_none_for_missing_id():
    assert get_strategy(99999) is None


def test_get_strategy_parses_dsl_columns_to_dicts():
    sid = _insert_strategy()
    s = get_strategy(sid)
    assert s["entry_dsl"] == _GOOD_ENTRY_DSL
    assert s["take_profit_dsl"] == _GOOD_PCT_DSL
    assert s["stop_loss_dsl"] == _GOOD_PCT_DSL
    assert s["notify_enabled"] is True
    assert s["state"] == "idle"


def test_list_enabled_strategies_filters_disabled_rows():
    on  = _insert_strategy(name="on",  notify_enabled=True)
    off = _insert_strategy(name="off", notify_enabled=False)
    enabled_ids = {s["id"] for s in list_enabled_strategies()}
    assert on  in enabled_ids
    assert off not in enabled_ids


def test_list_enabled_strategies_can_filter_by_contract():
    tx  = _insert_strategy(name="tx",  contract="TX")
    mtx = _insert_strategy(name="mtx", contract="MTX")
    tx_only = list_enabled_strategies(contract="TX")
    assert {s["id"] for s in tx_only} == {tx}


def test_update_strategy_state_writes_only_passed_keys():
    sid = _insert_strategy()
    update_strategy_state(sid, state="pending_entry",
                          entry_signal_date="2026-01-15")
    s = get_strategy(sid)
    assert s["state"] == "pending_entry"
    assert s["entry_signal_date"] == "2026-01-15"
    # Untouched columns stay null
    assert s["entry_fill_price"] is None


def test_update_strategy_state_can_clear_to_null():
    sid = _insert_strategy()
    update_strategy_state(sid, state="open",
                          entry_signal_date="2026-01-15",
                          entry_fill_date="2026-01-16",
                          entry_fill_price=17000.0)
    update_strategy_state(sid, state="idle",
                          entry_signal_date=None,
                          entry_fill_date=None,
                          entry_fill_price=None)
    s = get_strategy(sid)
    assert s["state"] == "idle"
    assert s["entry_signal_date"] is None
    assert s["entry_fill_price"] is None


def test_update_strategy_state_rejects_unknown_field():
    sid = _insert_strategy()
    with pytest.raises(ValueError, match="unknown"):
        update_strategy_state(sid, evil_field=1)


def test_write_signal_and_list_signals_round_trip():
    sid = _insert_strategy()
    write_signal(sid, kind="ENTRY_SIGNAL", signal_date="2026-01-15",
                 close_at_signal=17250.0)
    write_signal(sid, kind="ENTRY_FILLED", signal_date="2026-01-16",
                 fill_price=17260.0)
    write_signal(sid, kind="EXIT_SIGNAL", signal_date="2026-01-22",
                 close_at_signal=17600.0, exit_reason="TAKE_PROFIT")
    signals = list_signals(sid, limit=10)
    # Sorted DESC by signal_date — newest first
    assert [s["kind"] for s in signals] == [
        "EXIT_SIGNAL", "ENTRY_FILLED", "ENTRY_SIGNAL",
    ]
    assert signals[0]["exit_reason"] == "TAKE_PROFIT"
    assert signals[1]["fill_price"] == 17260.0


def test_mark_strategy_error_disables_and_records_message():
    sid = _insert_strategy()
    mark_strategy_error(sid, "ZeroDivisionError: bad math")
    s = get_strategy(sid)
    assert s["notify_enabled"] is False
    assert s["last_error"] == "ZeroDivisionError: bad math"
    assert s["last_error_at"] is not None


def test_mark_strategy_error_truncates_long_messages():
    sid = _insert_strategy()
    mark_strategy_error(sid, "x" * 5000)
    s = get_strategy(sid)
    assert len(s["last_error"]) <= 1000


from repositories.strategies import (
    create_strategy, update_strategy, delete_strategy, reset_strategy,
)


_GOOD_STRATEGY_INPUT = dict(
    user_id=1,
    name="rsi_reversion",
    direction="long",
    contract="TX",
    contract_size=1,
    max_hold_days=10,
    entry_dsl=_GOOD_ENTRY_DSL,
    take_profit_dsl=_GOOD_PCT_DSL,
    stop_loss_dsl=_GOOD_PCT_DSL,
)


def test_create_strategy_round_trip():
    sid = create_strategy(**_GOOD_STRATEGY_INPUT)
    assert sid > 0
    s = get_strategy(sid)
    assert s["name"] == "rsi_reversion"
    assert s["direction"] == "long"
    assert s["contract"] == "TX"
    assert s["state"] == "idle"
    assert s["notify_enabled"] is False
    assert s["entry_dsl"] == _GOOD_ENTRY_DSL


def test_create_strategy_unique_per_user_name():
    create_strategy(**_GOOD_STRATEGY_INPUT)
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        create_strategy(**_GOOD_STRATEGY_INPUT)


def test_update_strategy_partial_fields():
    sid = create_strategy(**_GOOD_STRATEGY_INPUT)
    update_strategy(sid, name="new_name", contract_size=2,
                    notify_enabled=True)
    s = get_strategy(sid)
    assert s["name"] == "new_name"
    assert s["contract_size"] == 2
    assert s["notify_enabled"] is True
    assert s["direction"] == "long"
    assert s["entry_dsl"] == _GOOD_ENTRY_DSL


def test_update_strategy_can_replace_dsl_columns():
    sid = create_strategy(**_GOOD_STRATEGY_INPUT)
    new_dsl = {"version": 1, "all": [
        {"left": {"field": "high"}, "op": "lt", "right": {"const": 1}}]}
    update_strategy(sid, entry_dsl=new_dsl)
    assert get_strategy(sid)["entry_dsl"] == new_dsl


def test_update_strategy_rejects_unknown_field():
    sid = create_strategy(**_GOOD_STRATEGY_INPUT)
    with pytest.raises(ValueError, match="unknown"):
        update_strategy(sid, evil=1)


def test_delete_strategy_removes_row_and_signals():
    sid = create_strategy(**_GOOD_STRATEGY_INPUT)
    write_signal(sid, kind="ENTRY_SIGNAL", signal_date="2026-01-15",
                 close_at_signal=100.0)
    delete_strategy(sid)
    assert get_strategy(sid) is None
    assert list_signals(sid) == []


def test_reset_strategy_clears_state_and_signals_but_keeps_row():
    sid = create_strategy(**_GOOD_STRATEGY_INPUT)
    update_strategy_state(sid, state="open",
                          entry_signal_date="2026-01-15",
                          entry_fill_date="2026-01-16",
                          entry_fill_price=200.0)
    write_signal(sid, kind="ENTRY_SIGNAL", signal_date="2026-01-15",
                 close_at_signal=200.0)
    mark_strategy_error(sid, "previous failure")

    reset_strategy(sid)

    s = get_strategy(sid)
    assert s is not None
    assert s["state"] == "idle"
    assert s["entry_signal_date"] is None
    assert s["entry_fill_price"] is None
    assert s["last_error"] is None
    assert list_signals(sid) == []
