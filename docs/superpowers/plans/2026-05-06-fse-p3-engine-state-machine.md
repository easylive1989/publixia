# FSE Phase 3 — Live Engine + State Machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the P2 DSL pipeline into the daily fetcher path: every TX/MTX/TMF fetcher run advances each enabled strategy's hypothetical-position state machine by exactly one bar, writes ENTRY_SIGNAL / ENTRY_FILLED / EXIT_SIGNAL / EXIT_FILLED rows, and stops a misbehaving strategy via `last_error` + auto-disable. After P3, strategies you've inserted into the DB by hand will live-update each day; no Discord notifications yet (P4) and no API/UI surface (P4/P5).

**Architecture:** New `repositories/strategies.py` (CRUD + signal log), new `services/strategy_engine.py` (4-state machine + entrypoints), `services/strategy_notifier.py` log-only stubs (P4 swaps in real Discord). The existing `fetchers/futures.py` is refactored to share its FinMind logic across three symbols (TX/MTX/TMF) and each fetcher tail-calls `on_futures_data_written(symbol, date)` to drive the engine. The state-machine semantics are copy-faithful to the P2 conformance test's `_simulate_realtime`: signal at T → fill at T+1 → optionally exit at T+1 → exit fill at T+2.

**Deviation from spec §5.1 fan-in barrier:** The spec described a barrier that waits for all three fetchers to complete before calling `evaluate_all` once. P3 instead dispatches per-fetcher: each fetcher's success path calls `on_futures_data_written(its_symbol, date)` independently, and the engine only evaluates strategies on that symbol. Because each strategy is bound to exactly one contract (spec §3.2 `strategies.contract` is a single value), the per-fetcher dispatch is functionally equivalent to the barrier and avoids the bookkeeping of tracking which fetchers have completed. If a fetcher fails for one contract, that contract's strategies skip evaluation for the day; strategies on the other two contracts proceed normally — same behaviour the spec describes for the barrier model.

**Tech Stack:** Python 3.12 / SQLite / APScheduler / Backtrader-free (P2 stays pure-DSL here).

**Spec reference:** `docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md` §3.5 (state machine), §5 (engine), §7 (notifier — only the timing; bodies are P4), §9 (edge cases).

---

## File Structure

**Created:**
- `backend/repositories/strategies.py` — CRUD over `strategies` + `strategy_signals` tables. JSON columns (`entry_dsl`, `take_profit_dsl`, `stop_loss_dsl`) marshalled via `json.loads`/`json.dumps`. Helpers: `list_enabled_strategies(contract=None)`, `get_strategy(id)`, `update_strategy_state(id, **fields)`, `write_signal(...)`, `list_signals(strategy_id, limit)`, `mark_strategy_error(id, msg)`.
- `backend/services/strategy_engine.py` — `evaluate_one(strategy, today_bar)`, `evaluate_all(date)`, `on_futures_data_written(contract, date)`, plus the 4 internal handlers (`_try_entry`, `_fill_entry`, `_try_exit`, `_emit_exit_signal`, `_fill_exit`) and history/lookback helpers.
- `backend/services/strategy_notifier.py` — `notify_signal(strategy, kind, today_bar)` and `notify_runtime_error(strategy, error)`. P3 logs only; P4 will swap in real Discord.
- `tests/test_strategies_repo.py`
- `tests/test_strategy_notifier.py`
- `tests/test_strategy_engine.py` — unit tests for each state transition.
- `tests/test_futures_mtx_tmf.py` — smoke tests for the new fetchers + verification that `on_futures_data_written` is called.
- `tests/test_strategy_engine_conformance.py` — re-run P2's 50-seed conformance against the production state machine.

**Modified:**
- `backend/fetchers/futures.py` — generalise the FinMind fetch + parse functions to accept a `symbol`, add public functions `fetch_tw_futures_mtx()` and `fetch_tw_futures_tmf()`, hook each fetcher's success path to call `services.strategy_engine.on_futures_data_written(symbol, last_date)`. The existing `fetch_tw_futures()` keeps its TX-only behaviours (`save_indicator_snapshot`, `check_alerts("indicator", "tw_futures", ...)`) but also makes the same engine call.
- `backend/jobs/registry.py` — register `tw_futures_mtx` and `tw_futures_tmf` JobSpecs, both at `30 17 * * *` (TST, same as TX).

**Out of scope (deferred):**
- Discord webhook posting (notifier bodies stay log-only — P4).
- API endpoints + frontend (P4/P5).
- Backfilling strategies for missed days (P3 evaluates only the latest bar; gaps caused by fetcher outages are not retroactively played back).
- P2.5 follow-ups (Wilder smoothing, `BacktestResult.open_position`, shared `_compare`).

---

## Task 1 — `repositories/strategies.py`

**Files:**
- Create: `backend/repositories/strategies.py`
- Create: `tests/test_strategies_repo.py`

- [ ] **Step 1.1: Write the failing test file**

Create `tests/test_strategies_repo.py`:

```python
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
```

- [ ] **Step 1.2: Run — should fail with ImportError**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_strategies_repo.py -v
```

Expected: ModuleNotFoundError on `repositories.strategies`.

- [ ] **Step 1.3: Implement the repo**

Create `backend/repositories/strategies.py`:

```python
"""Strategies + strategy_signals repository.

JSON columns (entry_dsl, take_profit_dsl, stop_loss_dsl) are stored as
TEXT in SQLite and parsed/serialised at the boundary so callers always
work with native Python dicts.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from db.connection import get_connection


_ALLOWED_STATE_FIELDS = {
    "state",
    "entry_signal_date", "entry_fill_date", "entry_fill_price",
    "pending_exit_kind", "pending_exit_signal_date",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _row_to_strategy(row) -> dict:
    d = dict(row)
    d["entry_dsl"]       = json.loads(d["entry_dsl"])
    d["take_profit_dsl"] = json.loads(d["take_profit_dsl"])
    d["stop_loss_dsl"]   = json.loads(d["stop_loss_dsl"])
    d["notify_enabled"]  = bool(d["notify_enabled"])
    return d


def list_enabled_strategies(contract: str | None = None) -> list[dict]:
    """Strategies with notify_enabled=1, optionally on a single contract."""
    sql = "SELECT * FROM strategies WHERE notify_enabled = 1"
    args: tuple = ()
    if contract:
        sql += " AND contract = ?"
        args = (contract,)
    sql += " ORDER BY id"
    with get_connection() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row_to_strategy(r) for r in rows]


def get_strategy(strategy_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM strategies WHERE id = ?", (strategy_id,),
        ).fetchone()
    return _row_to_strategy(row) if row else None


def update_strategy_state(strategy_id: int, **fields) -> None:
    """Update one or more state-machine columns. Pass None to set NULL.

    Allowed keys: state, entry_signal_date, entry_fill_date,
    entry_fill_price, pending_exit_kind, pending_exit_signal_date.
    """
    bad = set(fields) - _ALLOWED_STATE_FIELDS
    if bad:
        raise ValueError(f"unknown state fields: {sorted(bad)}")
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at=?"
    values = list(fields.values()) + [_now_iso(), strategy_id]
    with get_connection() as conn:
        conn.execute(
            f"UPDATE strategies SET {sets} WHERE id=?", values,
        )
        conn.commit()


def write_signal(
    strategy_id: int, *,
    kind: str, signal_date: str,
    close_at_signal: float | None = None,
    fill_price: float | None = None,
    exit_reason: str | None = None,
    pnl_points: float | None = None,
    pnl_amount: float | None = None,
    message: str | None = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO strategy_signals "
            "(strategy_id, kind, signal_date, close_at_signal, fill_price, "
            " exit_reason, pnl_points, pnl_amount, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (strategy_id, kind, signal_date, close_at_signal, fill_price,
             exit_reason, pnl_points, pnl_amount, message, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid


def list_signals(strategy_id: int, limit: int = 50) -> list[dict]:
    """Newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM strategy_signals WHERE strategy_id=? "
            "ORDER BY signal_date DESC, id DESC LIMIT ?",
            (strategy_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_strategy_error(strategy_id: int, error_message: str) -> None:
    """Set last_error + last_error_at and disable real-time notifications.
    The message is truncated to 1000 chars to fit a sane log surface."""
    msg = (error_message or "")[:1000]
    now = _now_iso()
    with get_connection() as conn:
        conn.execute(
            "UPDATE strategies SET "
            "  last_error = ?, last_error_at = ?, "
            "  notify_enabled = 0, updated_at = ? "
            "WHERE id = ?",
            (msg, now, now, strategy_id),
        )
        conn.commit()
```

- [ ] **Step 1.4: Run — should pass**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_strategies_repo.py -v
```

Expected: 10 tests PASS.

- [ ] **Step 1.5: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 336 + 10 = 346 PASS.

- [ ] **Step 1.6: Commit**

```bash
cd /Users/paulwu/Documents/Github/publixia
git add backend/repositories/strategies.py tests/test_strategies_repo.py
git commit -m "$(cat <<'EOF'
feat(strategy): repositories.strategies CRUD + signal log

list_enabled_strategies (optional contract filter), get_strategy,
update_strategy_state with allowlisted columns, write_signal,
list_signals (newest first), mark_strategy_error (truncates to 1000
chars + disables notify_enabled + stamps last_error_at).

DSL columns are TEXT in DB but parse to dicts at the boundary so
callers always see native Python.
EOF
)"
```

Do NOT amend, do NOT push.

---

## Task 2 — `services/strategy_notifier.py` (log-only stubs)

**Files:**
- Create: `backend/services/strategy_notifier.py`
- Create: `tests/test_strategy_notifier.py`

P3 ships log-only implementations so the engine has a stable interface. P4 swaps the function bodies to send actual Discord webhook payloads (per-user URL stored on `users.discord_webhook_url`, plus the global `discord_ops_webhook_url` for runtime errors).

- [ ] **Step 2.1: Write the failing tests**

Create `tests/test_strategy_notifier.py`:

```python
"""Tests for the P3 stub notifier — verifies the log call shape."""
import logging

from services.strategy_notifier import notify_signal, notify_runtime_error


def test_notify_signal_logs_strategy_kind_and_bar(caplog):
    strategy = {
        "id": 42, "user_id": 1,
        "contract": "TX", "direction": "long",
    }
    today_bar = {"date": "2026-05-15", "close": 17250.5}

    with caplog.at_level(logging.INFO):
        notify_signal(strategy, "ENTRY_SIGNAL", today_bar)

    msg = "\n".join(caplog.messages)
    assert "ENTRY_SIGNAL" in msg
    assert "strategy_id=42" in msg
    assert "user_id=1" in msg
    assert "contract=TX" in msg
    assert "2026-05-15" in msg


def test_notify_runtime_error_logs_strategy_id_and_msg(caplog):
    strategy = {"id": 7, "user_id": 1}
    err = ValueError("DSL exploded")

    with caplog.at_level(logging.WARNING):
        notify_runtime_error(strategy, err)

    msg = "\n".join(caplog.messages)
    assert "strategy_id=7" in msg
    assert "DSL exploded" in msg


def test_notify_runtime_error_truncates_long_message(caplog):
    strategy = {"id": 7, "user_id": 1}
    err = ValueError("x" * 2000)
    with caplog.at_level(logging.WARNING):
        notify_runtime_error(strategy, err)
    # The log line should not contain the full 2000 'x's.
    assert "x" * 600 not in caplog.text
```

- [ ] **Step 2.2: Run — should fail with ImportError**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_strategy_notifier.py -v
```

Expected: ModuleNotFoundError on `services.strategy_notifier`.

- [ ] **Step 2.3: Implement the stub**

Create `backend/services/strategy_notifier.py`:

```python
"""Strategy notifier — P3 stub.

The engine calls these on every state transition that should produce a
user-visible notification. P3 ships log-only bodies so the state machine
has a stable interface. P4 will swap them to:
  - notify_signal: post a Discord embed to users.discord_webhook_url
    (with system fallback if the user hasn't configured one).
  - notify_runtime_error: dual-channel post (user + ops global webhook).
"""
import logging

logger = logging.getLogger(__name__)


def notify_signal(strategy: dict, kind: str, today_bar: dict) -> None:
    """Called on ENTRY_SIGNAL or EXIT_SIGNAL writes. P3: log only."""
    logger.info(
        "strategy_notify_signal "
        "strategy_id=%s user_id=%s kind=%s contract=%s direction=%s "
        "signal_date=%s close=%s",
        strategy.get("id"),
        strategy.get("user_id"),
        kind,
        strategy.get("contract"),
        strategy.get("direction"),
        today_bar.get("date"),
        today_bar.get("close"),
    )


def notify_runtime_error(strategy: dict, error: Exception) -> None:
    """Called when evaluate_one() raises. P3: log only.
    Message is truncated to 500 chars to keep the log line legible."""
    logger.warning(
        "strategy_notify_runtime_error "
        "strategy_id=%s user_id=%s error=%s",
        strategy.get("id"),
        strategy.get("user_id"),
        str(error)[:500],
    )
```

- [ ] **Step 2.4: Run — should pass**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_strategy_notifier.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 2.5: Full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 349 PASS.

- [ ] **Step 2.6: Commit**

```bash
git add backend/services/strategy_notifier.py tests/test_strategy_notifier.py
git commit -m "$(cat <<'EOF'
feat(strategy): notifier stubs (P3 log-only, P4 will add Discord)

Two functions: notify_signal (called on ENTRY_SIGNAL / EXIT_SIGNAL
writes) and notify_runtime_error (called when evaluate_one raises).
Both log structured key=value lines; P4 will swap the bodies to post
Discord embeds without the engine needing to change.
EOF
)"
```

---

## Task 3 — `services/strategy_engine.py` state machine

**Files:**
- Create: `backend/services/strategy_engine.py`
- Create: `tests/test_strategy_engine.py`

The state machine is a faithful copy of the P2 conformance test's `_simulate_realtime` (see `tests/strategies/test_dsl_conformance.py` for the reference). Key invariants:

- `entry_signal_date` is **the bar where the entry signal fired** (i.e., yesterday from `_fill_entry`'s perspective). Held-days for `max_hold_days` is measured from `entry_signal_date`, not `entry_fill_date`.
- A single `evaluate_one(strategy, today_bar)` call may chain multiple state transitions on the same bar:
  - `pending_entry` on bar T+1: fill → state=open → check exits on the same T+1 bar.
  - `pending_exit` on bar E+1: fill exit → state=idle → check entry on the same E+1 bar.
- All DB writes go through `repositories.strategies`. Errors raised inside any handler get caught at the top-level, the strategy is marked `last_error` + auto-disabled, and `notify_runtime_error` fires.

- [ ] **Step 3.1: Write the failing engine tests**

Create `tests/test_strategy_engine.py`:

```python
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
    # Pass a today_bar missing the 'close' key — compute_expr raises KeyError.
    bad_bar = {"date": "2026-01-15", "open": 1.0, "high": 1.0, "low": 1.0,
               "volume": 1}    # no close
    _seed_bars("TX", [_bar("2026-01-15", 1.0)])

    s = get_strategy(sid)
    evaluate_one(s, bad_bar)

    s = get_strategy(sid)
    assert s["notify_enabled"] is False
    assert s["last_error"] is not None
```

- [ ] **Step 3.2: Run — should fail with ImportError**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_strategy_engine.py -v
```

Expected: ModuleNotFoundError on `services.strategy_engine`.

- [ ] **Step 3.3: Implement the engine**

Create `backend/services/strategy_engine.py`:

```python
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
from repositories.futures import get_futures_daily_range
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
    entry = EntryDSL.model_validate(strategy["entry_dsl"])
    history = _history_for(strategy, today_bar, entry.all)
    fired = run_dsl(entry, history)
    if fired is not True:        # False or None — not firing
        return
    write_signal(
        strategy["id"], kind="ENTRY_SIGNAL",
        signal_date=today_bar["date"],
        close_at_signal=today_bar["close"],
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
    """Bars window large enough to evaluate every condition's expressions."""
    n_required = max(
        (max(required_lookback(c.left), required_lookback(c.right)) for c in conds),
        default=1,
    )
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
```

- [ ] **Step 3.4: Run — should pass**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_strategy_engine.py -v
```

Expected: 9 tests PASS.

If `test_open_max_hold_days_uses_signal_date_not_fill_date` fails: confirm `_trading_days_between` is using `entry_signal_date` (not `entry_fill_date`); confirm the test setup seeds bars between signal and today so the count returns ≥ max_hold_days.

If `test_evaluate_one_marks_strategy_error_on_exception` fails because the bad-bar didn't actually raise: it's possible `compute_expr` returns None (defer) instead of raising for missing keys. In that case, change the test to inject a different failure mode — e.g., DSL with an `n` that isn't in the parsed expr's allowed range — but the simplest is to monkeypatch `run_dsl` to raise.

- [ ] **Step 3.5: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 358 PASS.

- [ ] **Step 3.6: Commit**

```bash
git add backend/services/strategy_engine.py tests/test_strategy_engine.py
git commit -m "$(cat <<'EOF'
feat(strategy): live state-machine engine

evaluate_one(strategy, today_bar) advances one strategy by one bar with
the four-state machine matching the P2 conformance test:

  idle → pending_entry → open → pending_exit → idle

Two phases per call: fill-then-test. pending_entry fills + may try_exit
on the same bar; pending_exit fills + may try_entry on the same bar.
max_hold_days is measured from entry_signal_date (signal time) so the
held-day count matches Backtrader's _entry_bar_idx semantics.

Top-level try/except marks runtime errors, auto-disables the strategy,
and fires notify_runtime_error. evaluate_all + on_futures_data_written
are the public entrypoints fetchers will call in Task 5.
EOF
)"
```

---

## Task 4 — Refactor `fetchers/futures.py` to support multiple symbols

**Files:**
- Modify: `backend/fetchers/futures.py`
- Create: `tests/test_futures_mtx_tmf.py`

We add `MTX` and `TMF` fetchers. They share 90% of `fetch_tw_futures`'s logic, so we generalise the FinMind request + parser to take a `symbol` parameter. TX-specific behaviours (`_save_indicator_snapshot`, the dashboard `check_alerts`) stay TX-only; MTX/TMF write only to `futures_daily`.

The strategy engine call (`on_futures_data_written`) is added to the shared path so all three contracts trigger it.

- [ ] **Step 4.1: Write the failing fetcher tests**

Create `tests/test_futures_mtx_tmf.py`:

```python
"""Smoke tests for MTX/TMF fetchers + verify the strategy engine hook fires."""
from unittest.mock import patch

from db.connection import get_connection
from fetchers import futures as mod
from repositories.futures import get_futures_daily_range


def _mock_finmind_response(symbol: str) -> list[dict]:
    """Two trading days, two contracts each — front-month is the higher-volume one."""
    return [
        {"date": "2026-04-01", "contract_date": "202604",
         "open": 17000, "max": 17100, "min": 16900, "close": 17050,
         "volume": 12345, "settlement_price": 17050,
         "open_interest": 100, "trading_session": "position"},
        {"date": "2026-04-02", "contract_date": "202604",
         "open": 17100, "max": 17200, "min": 17050, "close": 17180,
         "volume": 12000, "settlement_price": 17180,
         "open_interest": 110, "trading_session": "position"},
    ]


def test_fetch_mtx_writes_rows_under_mtx_symbol(monkeypatch):
    monkeypatch.setattr(
        mod, "_request",
        lambda symbol, start, end: _mock_finmind_response(symbol),
    )
    called = []
    monkeypatch.setattr(
        "services.strategy_engine.on_futures_data_written",
        lambda contract, date: called.append((contract, date)),
    )

    ok = mod.fetch_tw_futures_mtx()
    assert ok is True

    rows = get_futures_daily_range("MTX", "2026-04-01")
    assert {r["date"] for r in rows} == {"2026-04-01", "2026-04-02"}
    # No TX rows should have been written by the MTX fetcher.
    assert get_futures_daily_range("TX", "2026-04-01") == []

    assert called == [("MTX", "2026-04-02")]


def test_fetch_tmf_writes_rows_under_tmf_symbol(monkeypatch):
    monkeypatch.setattr(
        mod, "_request",
        lambda symbol, start, end: _mock_finmind_response(symbol),
    )
    called = []
    monkeypatch.setattr(
        "services.strategy_engine.on_futures_data_written",
        lambda contract, date: called.append((contract, date)),
    )

    assert mod.fetch_tw_futures_tmf() is True

    rows = get_futures_daily_range("TMF", "2026-04-01")
    assert len(rows) == 2
    assert called == [("TMF", "2026-04-02")]


def test_fetch_tw_still_works_and_calls_engine(monkeypatch):
    monkeypatch.setattr(
        mod, "_request",
        lambda symbol, start, end: _mock_finmind_response(symbol),
    )
    called = []
    monkeypatch.setattr(
        "services.strategy_engine.on_futures_data_written",
        lambda contract, date: called.append((contract, date)),
    )

    assert mod.fetch_tw_futures() is True

    assert {r["date"] for r in get_futures_daily_range("TX", "2026-04-01")} == {
        "2026-04-01", "2026-04-02",
    }
    # TX hook fires too — engine must see all three contracts.
    assert called == [("TX", "2026-04-02")]
```

- [ ] **Step 4.2: Run — should fail**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_futures_mtx_tmf.py -v
```

Expected: AttributeError on `fetch_tw_futures_mtx` / `fetch_tw_futures_tmf`, or test_fetch_tw fails because the engine hook doesn't yet fire from `fetch_tw_futures`.

- [ ] **Step 4.3: Refactor `backend/fetchers/futures.py`**

Replace the entire file content (preserving the FINMIND_URL / TOKEN setup and `parse_front_month` semantics) with this version:

```python
"""台灣指數期貨 fetchers — TX (大台), MTX (小台), TMF (微台)。

Source: FinMind TaiwanFuturesDaily,免費 dataset。每天每口合約一筆,
每個 symbol 都選每日成交量最大的一筆作為「近月連續合約」寫入
futures_daily 表。

TX 額外把當日 close + 漲跌幅寫入 indicator_snapshots(讓 dashboard 卡
片用既有的 history 機制讀取),並會觸發 indicator alert。MTX/TMF 不
需要這個——它們只是給策略引擎讀的 OHLCV 來源。

每個 symbol 寫完當日 row 之後都會 call services.strategy_engine.
on_futures_data_written(symbol, last_date) 推進相關策略的 state
machine。

Lazy fetch + DB cache:首次拉 5 年,之後只補 delta。
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import (
    save_futures_daily_rows, get_latest_futures_date, get_futures_daily_range,
    save_indicator,
)
from core.settings import settings
from alerts import check_alerts

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = settings.finmind_token.get_secret_value().strip()

DATASET = "TaiwanFuturesDaily"
INITIAL_LOOKBACK_DAYS = 365 * 5  # 首次抓 5 年


def _request(symbol: str, start_date: str, end_date: str) -> list[dict]:
    params = {
        "dataset":    DATASET,
        "data_id":    symbol,
        "start_date": start_date,
        "end_date":   end_date,
    }
    headers = {}
    if FINMIND_TOKEN:
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"
    r = requests.get(FINMIND_URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"FinMind {DATASET} error: {payload.get('msg') or payload}")
    return payload.get("data") or []


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _is_day_session(row: dict) -> bool:
    sess = row.get("trading_session")
    if sess is None:
        return True
    return sess in ("position", "Position")


def parse_front_month(rows: list[dict], symbol: str) -> list[dict]:
    """每日選成交量最大的合約 = 近月連續。"""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        d = r.get("date")
        if not d or not _is_day_session(r):
            continue
        vol = _safe_float(r.get("volume"))
        if vol is None or vol <= 0:
            continue
        by_day[d].append(r)

    out: list[dict] = []
    for d, group in by_day.items():
        pick = max(group, key=lambda r: _safe_float(r.get("volume")) or 0)
        out.append({
            "symbol":        symbol,
            "date":          d,
            "contract_date": pick.get("contract_date"),
            "open":          _safe_float(pick.get("open")),
            "high":          _safe_float(pick.get("max")),
            "low":           _safe_float(pick.get("min")),
            "close":         _safe_float(pick.get("close")),
            "volume":        _safe_float(pick.get("volume")),
            "open_interest": _safe_float(pick.get("open_interest")),
            "settlement":    _safe_float(pick.get("settlement_price")),
        })
    out.sort(key=lambda r: r["date"])
    return out


def _save_indicator_snapshot(rows: list[dict]) -> None:
    """TX-only: feed dashboard's tw_futures sparkline."""
    prev_close = None
    for r in rows:
        close = r.get("close")
        if close is None:
            continue
        change_pct = 0.0
        if prev_close:
            change_pct = round((close - prev_close) / prev_close * 100, 2)
        save_indicator(
            "tw_futures",
            close,
            json.dumps({
                "change_pct": change_pct,
                "prev_close": round(prev_close, 2) if prev_close else round(close, 2),
                "volume":     r.get("volume"),
                "contract":   r.get("contract_date"),
            }),
            date=r["date"],
        )
        prev_close = close


def _fetch_for_symbol(symbol: str, *, save_indicator_snapshot: bool,
                     lookback_days: int | None = None) -> bool:
    """Shared FinMind fetch + parse + persist + engine hook for any symbol."""
    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_futures_date(symbol)
    if latest:
        latest_date = datetime.strptime(latest, "%Y-%m-%d").date()
        if (today - latest_date).days <= 0:
            return True
        start = latest_date - timedelta(days=7)
    else:
        days = lookback_days or INITIAL_LOOKBACK_DAYS
        start = today - timedelta(days=days)
    start_date = start.strftime("%Y-%m-%d")
    if start_date > end_date:
        return True

    try:
        raw = _request(symbol, start_date, end_date)
    except Exception as e:
        print(f"[{symbol.lower()}] fetch error: {e}")
        return False

    parsed = parse_front_month(raw, symbol=symbol)
    if not parsed:
        return True
    save_futures_daily_rows(parsed)

    if save_indicator_snapshot:
        _save_indicator_snapshot(parsed)
        last_close = parsed[-1].get("close")
        if last_close is not None:
            check_alerts("indicator", "tw_futures", last_close)

    last_date = parsed[-1].get("date")
    if last_date:
        # Imported here (not at module top) to avoid a circular import on
        # backend startup: services.strategy_engine pulls in repositories
        # which pull in db, which calls fetchers' init code in some
        # tests via init_db's seeding path.
        from services.strategy_engine import on_futures_data_written
        on_futures_data_written(symbol, last_date)

    print(f"[{symbol.lower()}] {start_date}~{end_date}: {len(parsed)} day-rows")
    return True


# ── public entrypoints ──────────────────────────────────────────────

def fetch_tw_futures(lookback_days: int | None = None) -> bool:
    """大台 (TX) — also feeds the dashboard sparkline + alerts."""
    return _fetch_for_symbol("TX", save_indicator_snapshot=True,
                             lookback_days=lookback_days)


def fetch_tw_futures_mtx(lookback_days: int | None = None) -> bool:
    """小台 (MTX) — strategy engine only, no dashboard side effects."""
    return _fetch_for_symbol("MTX", save_indicator_snapshot=False,
                             lookback_days=lookback_days)


def fetch_tw_futures_tmf(lookback_days: int | None = None) -> bool:
    """微台 (TMF) — strategy engine only, no dashboard side effects."""
    return _fetch_for_symbol("TMF", save_indicator_snapshot=False,
                             lookback_days=lookback_days)


# Expose for routes layer (back-compat: TX-only history endpoint).
def get_tw_futures_history(since_date: str) -> list[dict]:
    return get_futures_daily_range("TX", since_date)
```

- [ ] **Step 4.4: Run — should pass**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_futures_mtx_tmf.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 4.5: Run pre-existing futures tests too**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_futures.py tests/test_fetchers.py -v 2>&1 | tail -25
```

Expected: every pre-existing TX test still passes (the refactor preserves the public surface). If anything fails on a `_request(start, end)`-style call site (the function now requires `symbol` as the first arg), search for `_request(` in the test file and update the mock signature to match.

- [ ] **Step 4.6: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 358 + 3 = 361 PASS.

- [ ] **Step 4.7: Commit**

```bash
git add backend/fetchers/futures.py tests/test_futures_mtx_tmf.py
git commit -m "$(cat <<'EOF'
feat(strategy): MTX + TMF fetchers + engine hook in TX/MTX/TMF tail

Generalise the FinMind fetch path to take a `symbol` parameter and add
two thin public functions: fetch_tw_futures_mtx + fetch_tw_futures_tmf.
TX keeps its dashboard side effects (indicator snapshot + check_alerts);
MTX/TMF write only to futures_daily.

All three fetchers now tail-call services.strategy_engine.
on_futures_data_written(symbol, last_date) so any enabled strategy on
that contract advances its state machine. Imports the engine lazily
inside the function to avoid a startup-time cycle.
EOF
)"
```

---

## Task 5 — Register MTX / TMF jobs in the scheduler

**Files:**
- Modify: `backend/jobs/registry.py`

The two new fetchers need scheduler entries; otherwise they're never called in production. Default cron is the same as TX (`30 17 * * *` TST = after 13:45 close).

- [ ] **Step 5.1: Edit `backend/jobs/registry.py`**

Find the existing import block at the top:

```python
from fetchers.futures import fetch_tw_futures
```

Replace it with:

```python
from fetchers.futures import (
    fetch_tw_futures, fetch_tw_futures_mtx, fetch_tw_futures_tmf,
)
```

Find the `JOBS` dict; locate the existing `"tw_futures"` entry and insert two new entries immediately after it. The block changes from:

```python
    "tw_futures":         JobSpec(fetch_tw_futures,           "30 17 * * *",  "台指期 (TX) 日線"),
```

to:

```python
    "tw_futures":         JobSpec(fetch_tw_futures,           "30 17 * * *",  "台指期 (TX) 日線"),
    "tw_futures_mtx":     JobSpec(fetch_tw_futures_mtx,       "30 17 * * *",  "小台指期 (MTX) 日線"),
    "tw_futures_tmf":     JobSpec(fetch_tw_futures_tmf,       "30 17 * * *",  "微台指期 (TMF) 日線"),
```

- [ ] **Step 5.2: Smoke check — registry loads cleanly**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -c "import sys; sys.path.insert(0, 'backend'); from jobs.registry import JOBS; print(sorted(JOBS))"
```

Expected output includes `tw_futures_mtx` and `tw_futures_tmf` between `tw_futures` and other entries. No traceback.

- [ ] **Step 5.3: Run full test suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 361 PASS (no behaviour change for tests; the registry is only consumed at scheduler boot, which is mocked or skipped in tests).

- [ ] **Step 5.4: Commit**

```bash
git add backend/jobs/registry.py
git commit -m "$(cat <<'EOF'
feat(scheduler): register MTX/TMF futures fetcher jobs

Both default to 30 17 * * * TST (after the 13:45 day-session close,
matching TX's cadence). The scheduler_jobs table will pick them up at
the next backend restart and admins can retime via the admin CLI as
usual.
EOF
)"
```

---

## Task 6 — End-to-end conformance regression against the production state machine

**Files:**
- Create: `tests/test_strategy_engine_conformance.py`

This is the keystone test for P3: the production state-machine path (`evaluate_one`) must produce the same closed-trade timeline as the P2 conformance test's `_simulate_realtime` for every one of the 50 random seeds. If they diverge, P3 has drifted from the spec's "live ↔ backtest must agree" guarantee.

The test re-uses `tests/strategies/random_dsl_generator.py` and the synthetic-bars fixture from `tests/strategies/conftest.py`.

- [ ] **Step 6.1: Write the conformance test**

Create `tests/test_strategy_engine_conformance.py`:

```python
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

    # Reconstruct trades from EXIT_FILLED + matching ENTRY_FILLED.
    sigs = list_signals(strategy_id, limit=10_000)
    sigs.reverse()  # oldest first
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
```

- [ ] **Step 6.2: Run the conformance regression**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_strategy_engine_conformance.py -v 2>&1 | tail -40
```

Expected: 50 PASS.

If 1–5 seeds fail with an off-by-one (engine fires one bar earlier or later than reference): inspect the failing seed's trade lists. Likely culprit is `_trading_days_between`'s boundary condition — confirm the count is `len([r for r in rows if signal_date < r["date"] <= today_date])` (strict on signal, inclusive on today). If the held-day count is wrong by 1, this is the place.

If many seeds fail with wildly different trade counts: the chained transitions inside `evaluate_one` aren't matching the simulator. Print the strategy_signals rows for one failing seed; the order should be ENTRY_SIGNAL → ENTRY_FILLED → (maybe more cycles) → EXIT_SIGNAL → EXIT_FILLED. If you see ENTRY_SIGNAL with no FILL on next bar, the pending_entry → open transition is firing on the wrong bar.

If you make code changes to the engine, commit them as separate small commits BEFORE the conformance commit:
- e.g., `fix(strategy): align _trading_days_between with conformance reference`
- Each fix commit should leave the full test suite green.

- [ ] **Step 6.3: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 411 PASS (361 + 50 conformance seeds).

- [ ] **Step 6.4: Commit the conformance test**

```bash
git add tests/test_strategy_engine_conformance.py
git commit -m "$(cat <<'EOF'
test(strategy): production engine conforms to P2 reference for 50 seeds

For each of the 50 random valid DSLs, insert as a strategies row, walk
the 250-bar fixture calling evaluate_one each day, reconstruct closed
trades from strategy_signals (pair ENTRY_FILLED ↔ EXIT_FILLED), and
assert the trade timeline equals the P2 conformance reference's
_simulate_realtime output. If they ever diverge, the live engine has
drifted from the spec's live ↔ backtest parity guarantee.
EOF
)"
```

---

## Phase exit criteria

After all six tasks are committed:

1. `python3 -m pytest tests/ -q` passes (≈411 tests).
2. `python3 -c "from services.strategy_engine import evaluate_one, evaluate_all, on_futures_data_written; from repositories.strategies import list_enabled_strategies, write_signal; print('ok')"` works from `backend/`.
3. `git log --oneline master..HEAD` shows the six (or more, if iteration was needed) phase commits.

P3 is then ready to merge. On deploy, the new MTX / TMF jobs land in `scheduler_jobs` (default cron `30 17 * * *`), the next 17:30 TST run starts populating `futures_daily` for all three contracts, and any pre-existing strategy with `notify_enabled=1` begins advancing its state machine. No Discord notifications yet — log lines only — so you can verify behaviour through `journalctl -u stock-dashboard.service -f` looking for `strategy_notify_signal` lines.

The next phase is **P4: API + Notifier**, which will:
- Add `repositories.strategies` write-side functions (create / update / delete) — P3 only added read + state.
- Add `api/routes/strategies.py` (CRUD + backtest endpoints).
- Replace the `services/strategy_notifier.py` stubs with real Discord posting (per-user webhook).
- Hook the admin CLI's webhook validation step into a real Discord test-message send.
