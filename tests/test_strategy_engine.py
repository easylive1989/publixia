"""Tests for services.strategy_engine — one transition per test."""
import json

import pytest

from db.connection import get_connection
from repositories.futures import save_futures_daily_rows
from repositories.strategies import get_strategy, list_signals
from services.strategy_engine import evaluate_one


# ── fixtures ────────────────────────────────────────────────────────

_ENTRY_ALWAYS_TRUE = {
    "version": 1,
    "all": [{"left": {"const": 0}, "op": "gte", "right": {"const": 0}}],
}
_ENTRY_CLOSE_GT_100 = {
    "version": 1,
    "all": [{"left": {"field": "close"}, "op": "gt",
             "right": {"const": 100}}],
}
_PCT_2 = {"version": 1, "type": "pct", "value": 2.0}


def _insert_strategy(*, entry_dsl=_ENTRY_ALWAYS_TRUE,
                     take_profit_dsl=_PCT_2, stop_loss_dsl=_PCT_2,
                     direction="long", contract="TX",
                     contract_size=1, max_hold_days=None,
                     state="idle",
                     entry_signal_date=None,
                     entry_fill_date=None,
                     entry_fill_price=None,
                     pending_exit_kind=None,
                     pending_exit_signal_date=None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO strategies "
            "(user_id, name, direction, contract, contract_size, "
            " max_hold_days, entry_dsl, take_profit_dsl, stop_loss_dsl, "
            " notify_enabled, state, entry_signal_date, entry_fill_date, "
            " entry_fill_price, pending_exit_kind, "
            " pending_exit_signal_date, created_at, updated_at) "
            "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, "
            " '2026-01-01T00:00:00', '2026-01-01T00:00:00')",
            (f"s_{state}", direction, contract, contract_size, max_hold_days,
             json.dumps(entry_dsl),
             json.dumps(take_profit_dsl),
             json.dumps(stop_loss_dsl),
             state,
             entry_signal_date, entry_fill_date, entry_fill_price,
             pending_exit_kind, pending_exit_signal_date),
        )
        conn.commit()
        return cur.lastrowid


def _seed_bars(symbol: str, bars: list[dict]) -> None:
    """Bulk-insert bars into futures_daily."""
    rows = [{
        "symbol": symbol, "date": b["date"],
        "contract_date": "202607",
        "open": b["open"], "high": b["high"], "low": b["low"],
        "close": b["close"], "volume": b.get("volume", 1000),
        "open_interest": None, "settlement": None,
    } for b in bars]
    save_futures_daily_rows(rows)


def _bar(date, close, *, open_=None, high=None, low=None, volume=1000):
    return {"date": date,
            "open":   open_ if open_ is not None else close,
            "high":   high  if high  is not None else close + 1,
            "low":    low   if low   is not None else close - 1,
            "close":  close, "volume": volume}


# ── idle → pending_entry ─────────────────────────────────────────────

def test_idle_with_firing_entry_writes_signal_and_advances():
    sid = _insert_strategy(entry_dsl=_ENTRY_CLOSE_GT_100, state="idle")
    today = _bar("2026-01-15", close=200.0)
    _seed_bars("TX", [today])

    s = get_strategy(sid)
    evaluate_one(s, today)

    s = get_strategy(sid)
    assert s["state"] == "pending_entry"
    assert s["entry_signal_date"] == "2026-01-15"
    signals = list_signals(sid)
    assert len(signals) == 1
    assert signals[0]["kind"] == "ENTRY_SIGNAL"
    assert signals[0]["close_at_signal"] == 200.0


def test_idle_with_failing_entry_writes_no_signal():
    sid = _insert_strategy(entry_dsl=_ENTRY_CLOSE_GT_100, state="idle")
    today = _bar("2026-01-15", close=50.0)
    _seed_bars("TX", [today])

    s = get_strategy(sid)
    evaluate_one(s, today)

    assert get_strategy(sid)["state"] == "idle"
    assert list_signals(sid) == []


# ── pending_entry → open (fill on next bar's open) ───────────────────

def test_pending_entry_fills_on_today_open_and_checks_exit_immediately():
    sid = _insert_strategy(
        state="pending_entry",
        entry_signal_date="2026-01-15",
        # No entry conditions can fire (state=pending_entry first)
        # But the chained _try_exit needs DSLs that don't fire —
        # use 100% pct so exit is unreachable.
        take_profit_dsl={"version": 1, "type": "pct", "value": 100.0},
        stop_loss_dsl={"version": 1, "type": "pct", "value": 100.0},
    )
    fill_bar = _bar("2026-01-16", close=210.0, open_=205.0)
    _seed_bars("TX", [fill_bar])

    s = get_strategy(sid)
    evaluate_one(s, fill_bar)

    s = get_strategy(sid)
    assert s["state"] == "open"
    assert s["entry_fill_date"] == "2026-01-16"
    assert s["entry_fill_price"] == 205.0
    signals = list_signals(sid)
    assert [r["kind"] for r in signals] == ["ENTRY_FILLED"]
    assert signals[0]["fill_price"] == 205.0


# ── open → pending_exit (stop_loss precedence) ───────────────────────

def test_open_with_stop_loss_triggered_emits_exit_signal():
    sid = _insert_strategy(
        state="open",
        entry_signal_date="2026-01-15",
        entry_fill_date="2026-01-16",
        entry_fill_price=200.0,
        take_profit_dsl={"version": 1, "type": "pct", "value": 5.0},
        stop_loss_dsl  ={"version": 1, "type": "pct", "value": 1.0},
    )
    today = _bar("2026-01-20", close=197.0)   # -1.5% triggers SL@1%
    _seed_bars("TX", [today])

    s = get_strategy(sid)
    evaluate_one(s, today)

    s = get_strategy(sid)
    assert s["state"] == "pending_exit"
    assert s["pending_exit_kind"] == "STOP_LOSS"
    assert s["pending_exit_signal_date"] == "2026-01-20"
    signals = list_signals(sid)
    assert signals[0]["kind"] == "EXIT_SIGNAL"
    assert signals[0]["exit_reason"] == "STOP_LOSS"


def test_engine_emits_exit_passes_real_kind_to_notifier():
    """Regression for C1: _emit_exit_signal must pass the just-decided
    exit_reason to the notifier so the embed renders the correct title /
    colour. Without this, every real take-profit / stop-loss would
    render as "🔧 手動平倉" because strategy["pending_exit_kind"] is
    still None at notify time."""
    from unittest.mock import patch
    sid = _insert_strategy(
        state="open",
        entry_signal_date="2026-01-15",
        entry_fill_date="2026-01-16",
        entry_fill_price=200.0,
        take_profit_dsl={"version": 1, "type": "pct", "value": 1.0},
        stop_loss_dsl  ={"version": 1, "type": "pct", "value": 5.0},
    )
    today = _bar("2026-01-20", close=205.0)   # +2.5% triggers TP@1%
    _seed_bars("TX", [today])

    captured = {}
    real_notify = None
    from services import strategy_engine as eng
    real_notify = eng.notify_signal

    def spy(strategy, kind, today_bar):
        captured["strategy"] = dict(strategy)   # snapshot
        captured["kind"]     = kind

    with patch.object(eng, "notify_signal", side_effect=spy):
        s = get_strategy(sid)
        evaluate_one(s, today)

    assert captured["kind"] == "EXIT_SIGNAL"
    assert captured["strategy"]["pending_exit_kind"] == "TAKE_PROFIT"


def test_open_max_hold_days_uses_signal_date_not_fill_date():
    """held = trading-days from entry_signal_date to today_date (inclusive
    of today, exclusive of signal_date). This matches BT's
    `held = len(self) - _entry_bar_idx` where _entry_bar_idx is the
    SIGNAL bar."""
    sid = _insert_strategy(
        state="open",
        max_hold_days=3,
        entry_signal_date="2026-01-15",
        entry_fill_date  ="2026-01-16",
        entry_fill_price =200.0,
        # Make TP / SL unreachable so only the timeout fires.
        take_profit_dsl={"version": 1, "type": "pct", "value": 100.0},
        stop_loss_dsl  ={"version": 1, "type": "pct", "value": 100.0},
    )
    bars = [
        _bar("2026-01-15", 200.0),  # signal day (already past)
        _bar("2026-01-16", 200.0),  # fill day; held=1
        _bar("2026-01-17", 200.0),  # held=2
        _bar("2026-01-18", 200.0),  # held=3 — TIMEOUT fires here
    ]
    _seed_bars("TX", bars)

    s = get_strategy(sid)
    evaluate_one(s, bars[3])

    s = get_strategy(sid)
    assert s["state"] == "pending_exit"
    assert s["pending_exit_kind"] == "TIMEOUT"


# ── pending_exit → idle (fill on today's open) ──────────────────────

def test_pending_exit_fills_and_logs_pnl_long():
    sid = _insert_strategy(
        direction="long", contract="TX", contract_size=1,
        state="pending_exit",
        entry_signal_date="2026-01-15",
        entry_fill_date  ="2026-01-16",
        entry_fill_price =200.0,
        pending_exit_kind="TAKE_PROFIT",
        pending_exit_signal_date="2026-01-22",
    )
    fill_bar = _bar("2026-01-23", close=215.0, open_=210.0)
    _seed_bars("TX", [fill_bar])

    s = get_strategy(sid)
    evaluate_one(s, fill_bar)

    s = get_strategy(sid)
    assert s["state"] == "idle"
    assert s["entry_fill_price"] is None
    assert s["pending_exit_kind"] is None

    signals = list_signals(sid)
    assert signals[0]["kind"] == "EXIT_FILLED"
    assert signals[0]["fill_price"] == 210.0
    assert signals[0]["exit_reason"] == "TAKE_PROFIT"
    # PnL: (210 - 200) * 200 (TX mult) * 1 (lot) = 2000
    assert signals[0]["pnl_amount"] == pytest.approx(2000.0)


def test_pending_exit_short_pnl_flips_sign():
    sid = _insert_strategy(
        direction="short",
        state="pending_exit",
        entry_signal_date="2026-01-15",
        entry_fill_date  ="2026-01-16",
        entry_fill_price =200.0,
        pending_exit_kind="STOP_LOSS",
        pending_exit_signal_date="2026-01-22",
    )
    fill_bar = _bar("2026-01-23", close=205.0, open_=210.0)
    _seed_bars("TX", [fill_bar])

    evaluate_one(get_strategy(sid), fill_bar)

    sig = list_signals(sid)[0]
    # Short PnL = entry_price - fill_price = 200 - 210 = -10 → loss
    assert sig["pnl_points"] == pytest.approx(-10.0)
    assert sig["pnl_amount"] == pytest.approx(-2000.0)


# ── pending_exit → idle → pending_entry on same bar (no cooldown) ───

def test_pending_exit_can_chain_to_new_entry_on_same_bar():
    sid = _insert_strategy(
        entry_dsl=_ENTRY_CLOSE_GT_100,
        direction="long",
        state="pending_exit",
        entry_signal_date="2026-01-15",
        entry_fill_date  ="2026-01-16",
        entry_fill_price =200.0,
        pending_exit_kind="TAKE_PROFIT",
        pending_exit_signal_date="2026-01-22",
    )
    fill_bar = _bar("2026-01-23", close=205.0, open_=204.0)  # >100 → entry fires
    _seed_bars("TX", [fill_bar])

    evaluate_one(get_strategy(sid), fill_bar)

    s = get_strategy(sid)
    assert s["state"] == "pending_entry"
    assert s["entry_signal_date"] == "2026-01-23"
    kinds = [r["kind"] for r in list_signals(sid)]
    assert kinds[0] == "ENTRY_SIGNAL"
    assert kinds[1] == "EXIT_FILLED"


# ── exception handling ──────────────────────────────────────────────

def test_evaluate_one_marks_strategy_error_on_exception():
    """If the DSL parses but evaluation raises (e.g., bar missing a field),
    the strategy should be auto-disabled and last_error set."""
    sid = _insert_strategy(state="idle")
    # Pass a today_bar missing the 'close' key — _try_entry's write_signal
    # call dereferences today_bar["close"] and raises KeyError.
    bad_bar = {"date": "2026-01-15", "open": 1.0, "high": 1.0, "low": 1.0,
               "volume": 1}    # no close
    _seed_bars("TX", [_bar("2026-01-15", 1.0)])

    s = get_strategy(sid)
    evaluate_one(s, bad_bar)

    s = get_strategy(sid)
    assert s["notify_enabled"] is False
    assert s["last_error"] is not None


def test_evaluate_one_runtime_error_writes_signal_row_visible_in_history():
    """When evaluate_one() raises, mark_strategy_error fires + the user
    sees a RUNTIME_ERROR row in list_signals."""
    sid = _insert_strategy(state="idle")
    bad_bar = {"date": "2026-01-15", "open": 1.0, "high": 1.0, "low": 1.0,
               "volume": 1}    # missing 'close' → KeyError in _try_entry
    _seed_bars("TX", [_bar("2026-01-15", 1.0)])

    s = get_strategy(sid)
    evaluate_one(s, bad_bar)

    sigs = list_signals(sid)
    kinds = [r["kind"] for r in sigs]
    assert "RUNTIME_ERROR" in kinds
