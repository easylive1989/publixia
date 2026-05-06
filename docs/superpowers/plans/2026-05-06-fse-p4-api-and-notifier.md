# FSE Phase 4 — API + Real Notifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the strategy engine over HTTP (12 endpoints under `/api/strategies/*`) and replace the P3 log-only notifier with real Discord webhook posts. After P4, the future P5 frontend has every API surface it needs, and a real strategy that fires `ENTRY_SIGNAL` will land an embed in the user's Discord webhook.

**Architecture:** New `backend/api/routes/strategies.py` (CRUD + state actions + signals + backtest) backed by additional write-side helpers in `backend/repositories/strategies.py`. Strategy access gated by `require_strategy_permission` (token-resolved user must have `can_use_strategy=1`). The notifier swaps log-only bodies for `core.discord.send_to_discord(webhook_url, payload)` calls — per-user webhook for signals, system-global webhook for ops-side runtime errors. Admin CLI's "set webhook" gains an immediate test-ping; "clear webhook" with active strategies offers cascade-disable.

**Tech Stack:** FastAPI / Pydantic 2 / Discord webhooks / pytest with TestClient.

**Spec reference:** `docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md` §7 (notifier), §8.1–8.3 (API + admin CLI), §9 (edge cases).

---

## File Structure

**Created:**
- `backend/api/routes/strategies.py` — 12 endpoints under `/api/strategies/*`.
- `backend/api/schemas/strategy.py` — Pydantic request/response models.
- `backend/api/strategy_dsl_schema.py` — static DSL metadata served by `GET /api/strategies/dsl/schema` (used by the P5 frontend's condition builder to enumerate fields/operators/indicators).
- `tests/test_strategies_routes.py`
- `tests/test_strategy_notifier_real.py`
- `tests/test_admin_webhook_test_message.py`

**Modified:**
- `backend/repositories/strategies.py` — add `create_strategy`, `update_strategy`, `delete_strategy`, `reset_strategy`. The P3 read-side helpers stay.
- `backend/services/strategy_notifier.py` — replace log-only bodies with Discord posts. Module surface (`notify_signal`, `notify_runtime_error`) does not change.
- `backend/services/strategy_engine.py` — add `force_close(strategy)` function.
- `backend/services/strategy_backtest.py` — add `run_backtest_from_db(strategy, start_date, end_date, ...)` that pulls bars from `futures_daily` and delegates to existing `run_backtest`.
- `backend/api/dependencies.py` — add `require_strategy_permission` dep.
- `backend/main.py` — register `strategies.router`.
- `tests/conftest.py` — extend `_fake_user` with the FSE columns; add `_fake_user_with_strategy_permission` override stub.
- `admin/ops.py` — `set_discord_webhook` returns a `WebhookSetResult` carrying whether a test ping succeeded; `clear_discord_webhook_with_cascade` warns about active strategies and optionally disables them.
- `admin/__main__.py` — surface the test-ping result; thread the cascade-disable confirmation prompt.

**Out of scope (deferred):**
- Frontend (P5).
- E2E test fixture + ADMIN.md additions (P6).
- P2.5 follow-ups (Wilder smoothing, `BacktestResult.open_position` split, shared `_compare`).
- Spec §11.3 dashboard documentation refresh — P6.

---

## Task 1 — Strategies repo: write side

**Files:**
- Modify: `backend/repositories/strategies.py`
- Modify: `tests/test_strategies_repo.py`

P3 added read helpers. P4 adds the create/update/delete/reset writers. Routes and admin tools call these.

- [ ] **Step 1.1: Append the failing tests**

Append to `tests/test_strategies_repo.py`:

```python
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
    assert s["notify_enabled"] is False    # default off
    assert s["entry_dsl"] == _GOOD_ENTRY_DSL


def test_create_strategy_unique_per_user_name():
    create_strategy(**_GOOD_STRATEGY_INPUT)
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        create_strategy(**_GOOD_STRATEGY_INPUT)   # same (user_id, name)


def test_update_strategy_partial_fields():
    sid = create_strategy(**_GOOD_STRATEGY_INPUT)
    update_strategy(sid, name="new_name", contract_size=2,
                    notify_enabled=True)
    s = get_strategy(sid)
    assert s["name"] == "new_name"
    assert s["contract_size"] == 2
    assert s["notify_enabled"] is True
    # Untouched fields stay.
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
    # cascade: strategy_signals rows are gone too (FK ON DELETE CASCADE).
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
```

- [ ] **Step 1.2: Run — should fail with ImportError**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_strategies_repo.py -v 2>&1 | tail -20
```

Expected: ImportError on `create_strategy` / `update_strategy` / `delete_strategy` / `reset_strategy`.

- [ ] **Step 1.3: Implement the writers**

Append to `backend/repositories/strategies.py`:

```python
_ALLOWED_UPDATE_FIELDS = {
    "name", "direction", "contract", "contract_size", "max_hold_days",
    "entry_dsl", "take_profit_dsl", "stop_loss_dsl",
    "notify_enabled",
}


def create_strategy(*,
                    user_id: int,
                    name: str,
                    direction: str,
                    contract: str,
                    contract_size: int,
                    entry_dsl: dict,
                    take_profit_dsl: dict,
                    stop_loss_dsl: dict,
                    max_hold_days: int | None = None,
                    notify_enabled: bool = False) -> int:
    """Insert a new strategy in `idle` state. Caller is responsible for
    pre-validating the DSL dicts (route layer does it via
    services.strategy_dsl.validator.validate)."""
    now = _now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO strategies "
            "(user_id, name, direction, contract, contract_size, "
            " max_hold_days, entry_dsl, take_profit_dsl, stop_loss_dsl, "
            " notify_enabled, state, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'idle', ?, ?)",
            (user_id, name, direction, contract, contract_size,
             max_hold_days,
             json.dumps(entry_dsl),
             json.dumps(take_profit_dsl),
             json.dumps(stop_loss_dsl),
             1 if notify_enabled else 0,
             now, now),
        )
        conn.commit()
        return cur.lastrowid


def update_strategy(strategy_id: int, **fields) -> None:
    """Update one or more user-editable fields. Pass keys from
    _ALLOWED_UPDATE_FIELDS. DSL fields are JSON-serialised; bool fields
    encoded to 0/1."""
    bad = set(fields) - _ALLOWED_UPDATE_FIELDS
    if bad:
        raise ValueError(f"unknown update fields: {sorted(bad)}")
    if not fields:
        return
    encoded: dict = {}
    for k, v in fields.items():
        if k in ("entry_dsl", "take_profit_dsl", "stop_loss_dsl"):
            encoded[k] = json.dumps(v)
        elif k == "notify_enabled":
            encoded[k] = 1 if v else 0
        else:
            encoded[k] = v
    sets = ", ".join(f"{k}=?" for k in encoded) + ", updated_at=?"
    values = list(encoded.values()) + [_now_iso(), strategy_id]
    with get_connection() as conn:
        conn.execute(
            f"UPDATE strategies SET {sets} WHERE id=?", values,
        )
        conn.commit()


def delete_strategy(strategy_id: int) -> None:
    """Hard delete + cascade signals (FK ON DELETE CASCADE in migration 0008)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM strategies WHERE id=?", (strategy_id,))
        conn.commit()


def reset_strategy(strategy_id: int) -> None:
    """Drop all signals + clear state machine columns + clear last_error.
    Keeps the strategy row itself; user can re-enable afterwards."""
    now = _now_iso()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM strategy_signals WHERE strategy_id=?",
            (strategy_id,),
        )
        conn.execute(
            "UPDATE strategies SET "
            "  state='idle', "
            "  entry_signal_date=NULL, entry_fill_date=NULL, "
            "  entry_fill_price=NULL, "
            "  pending_exit_kind=NULL, pending_exit_signal_date=NULL, "
            "  last_error=NULL, last_error_at=NULL, "
            "  updated_at=? "
            "WHERE id=?",
            (now, strategy_id),
        )
        conn.commit()
```

- [ ] **Step 1.4: Run — should pass**

```bash
python3 -m pytest tests/test_strategies_repo.py -v 2>&1 | tail -25
```

Expected: 17 tests PASS (10 from P3 + 7 new).

- [ ] **Step 1.5: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 411 + 7 = 418 PASS.

- [ ] **Step 1.6: Commit**

```bash
git add backend/repositories/strategies.py tests/test_strategies_repo.py
git commit -m "$(cat <<'EOF'
feat(strategy): repositories.strategies write side

create_strategy (insert in idle state, JSON-serialise the three DSL
columns), update_strategy with allowlisted fields (DSL fields and
notify_enabled get encoded), delete_strategy (cascade signals via FK),
reset_strategy (drop all signals + clear state machine + clear
last_error, but keep the row). Routes and admin tools land in
subsequent commits.
EOF
)"
```

---

## Task 2 — Pydantic schemas + DSL metadata

**Files:**
- Create: `backend/api/schemas/strategy.py`
- Create: `backend/api/strategy_dsl_schema.py`

These are the bodies of the request/response payloads + the static metadata the frontend consumes from `GET /api/strategies/dsl/schema`. Models are wired to routes in Tasks 4–7.

- [ ] **Step 2.1: Create the schemas module**

Create `backend/api/schemas/strategy.py`:

```python
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
```

- [ ] **Step 2.2: Create the DSL metadata module**

Create `backend/api/strategy_dsl_schema.py`:

```python
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
```

- [ ] **Step 2.3: Smoke-import**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -c "import sys; sys.path.insert(0, 'backend'); from api.schemas.strategy import StrategyCreate, BacktestRequest; from api.strategy_dsl_schema import DSL_SCHEMA; print('schemas ok, indicators=', [i['name'] for i in DSL_SCHEMA['indicators']])"
```

Expected: `schemas ok, indicators= ['sma', 'ema', 'rsi', 'macd', 'bbands', 'atr', 'kd', 'highest', 'lowest', 'change_pct']`

- [ ] **Step 2.4: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 418 PASS (no behaviour change).

- [ ] **Step 2.5: Commit**

```bash
git add backend/api/schemas/strategy.py backend/api/strategy_dsl_schema.py
git commit -m "$(cat <<'EOF'
feat(api): pydantic schemas + DSL metadata for /api/strategies/*

StrategyCreate / StrategyUpdate / StrategyResponse / SignalResponse /
BacktestRequest / BacktestResponse cover every body shape the route
module will serialise. extra='forbid' on every model so unexpected keys
fail validation loudly.

DSL_SCHEMA is the static metadata the frontend's condition builder
will read via GET /api/strategies/dsl/schema. Test assertions in later
tasks lock its indicator list in sync with services.strategy_dsl.models.
EOF
)"
```

---

## Task 3 — `require_strategy_permission` dependency + conftest fixup

**Files:**
- Modify: `backend/api/dependencies.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_me_route.py` (add a single regression test)

`require_strategy_permission` extends `require_user`: load the user's settings via `get_user_with_settings`, refuse if `can_use_strategy` is false. Tests for individual route gating land in Tasks 4–7; this task wires the dep + extends `_fake_user` so that the existing `/api/me` tests don't regress when `require_user` starts being asked for the strategy column.

- [ ] **Step 3.1: Extend `_fake_user` in `tests/conftest.py`**

In `tests/conftest.py`, replace `_fake_user` with:

```python
def _fake_user():
    """Bypass auth in tests — returns the seeded paul row.

    Includes the FSE columns that landed in P1 so tests for
    require_strategy_permission can override per-test by toggling
    can_use_strategy. Default mirrors a fresh DB row: no permission,
    no webhook configured."""
    return {
        "id":                  1,
        "name":                "paul",
        "created_at":          "2026-01-01T00:00:00",
        "can_use_strategy":    False,
        "discord_webhook_url": None,
    }
```

(Existing call sites use `user["id"]` / `user["name"]` only; the new keys are additive.)

- [ ] **Step 3.2: Append the dep + a quick `/api/me` regression test**

Append to `tests/test_me_route.py`:

```python
from api.dependencies import require_strategy_permission


def test_require_strategy_permission_403_when_off():
    """Default _fake_user has can_use_strategy=False; the dep rejects."""
    from fastapi import FastAPI
    app2 = FastAPI()

    @app2.get("/probe")
    def probe(user: dict = Depends(require_strategy_permission)):
        return {"ok": True}

    # Reuse the global require_user override so probe sees the lean dict
    # without can_use_strategy being toggled.
    from api.dependencies import require_user
    app2.dependency_overrides[require_user] = lambda: {
        "id": 1, "name": "paul",
        "can_use_strategy": False, "discord_webhook_url": None,
    }
    from fastapi.testclient import TestClient
    r = TestClient(app2).get("/probe")
    assert r.status_code == 403
    assert r.json()["detail"] == "no strategy permission"


def test_require_strategy_permission_passes_when_on():
    from fastapi import FastAPI
    app2 = FastAPI()

    @app2.get("/probe")
    def probe(user: dict = Depends(require_strategy_permission)):
        return {"name": user["name"]}

    from api.dependencies import require_user
    app2.dependency_overrides[require_user] = lambda: {
        "id": 1, "name": "paul",
        "can_use_strategy": True, "discord_webhook_url": "https://discord.com/api/webhooks/1/" + "x" * 60,
    }
    from fastapi.testclient import TestClient
    r = TestClient(app2).get("/probe")
    assert r.status_code == 200
    assert r.json() == {"name": "paul"}
```

Make sure the existing `from fastapi.testclient import TestClient` at the top stays; if `Depends` is not yet imported, add `from fastapi import Depends` to the top of the file.

- [ ] **Step 3.3: Run — both new tests should fail with ImportError**

```bash
python3 -m pytest tests/test_me_route.py -v
```

Expected: ImportError on `require_strategy_permission`.

- [ ] **Step 3.4: Implement the dep**

Append to `backend/api/dependencies.py`:

```python
from repositories.users import get_user_with_settings


async def require_strategy_permission(user: dict = Depends(require_user)) -> dict:
    """Extend require_user with the FSE feature gate.

    require_user returns the lean {id, name, created_at} shape from
    get_user_by_id. We re-query via get_user_with_settings to read the
    can_use_strategy flag. Caller receives the merged dict so route
    handlers can use either user["id"] or user["can_use_strategy"]
    without further DB calls.
    """
    settings = get_user_with_settings(user["id"])
    if settings is None or not settings["can_use_strategy"]:
        raise HTTPException(status_code=403, detail="no strategy permission")
    # Merge so callers see both shapes' fields.
    return {**user, **settings}
```

- [ ] **Step 3.5: Run tests — should pass**

```bash
python3 -m pytest tests/test_me_route.py -v 2>&1 | tail -15
```

Expected: 5 tests PASS (3 from P1 + 2 new).

- [ ] **Step 3.6: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 420 PASS.

- [ ] **Step 3.7: Commit**

```bash
git add backend/api/dependencies.py tests/conftest.py tests/test_me_route.py
git commit -m "$(cat <<'EOF'
feat(api): require_strategy_permission dependency

Extends require_user by re-loading the user via get_user_with_settings
and refusing 403 if can_use_strategy is False. Returned dict merges the
two shapes so route handlers see both id/name and the strategy flag /
webhook URL without an extra query.

conftest._fake_user now includes can_use_strategy + discord_webhook_url
in the test stub. Existing tests continue to read user["id"] / ["name"]
unchanged.
EOF
)"
```

---

## Task 4 — Read-only strategy endpoints

**Files:**
- Create: `backend/api/routes/strategies.py` (initial skeleton + read endpoints)
- Modify: `backend/main.py`
- Create: `tests/test_strategies_routes.py`

GET endpoints first because they're the easiest to test without exercising the writer side. POST/PATCH/DELETE land in Task 5.

- [ ] **Step 4.1: Write the failing tests**

Create `tests/test_strategies_routes.py`:

```python
"""Tests for /api/strategies/* — read endpoints only (Task 4)."""
import json

import pytest
from fastapi.testclient import TestClient

from db.connection import get_connection
from main import app
from repositories.strategies import create_strategy, write_signal


client = TestClient(app)


def _grant_permission_to_paul():
    with get_connection() as conn:
        conn.execute("UPDATE users SET can_use_strategy=1 WHERE id=1")
        conn.commit()


def _good_dsls():
    return dict(
        entry_dsl={"version": 1,
                   "all": [{"left": {"field": "close"}, "op": "gt",
                            "right": {"const": 100}}]},
        take_profit_dsl={"version": 1, "type": "pct", "value": 2.0},
        stop_loss_dsl  ={"version": 1, "type": "pct", "value": 1.0},
    )


def test_list_strategies_403_without_permission():
    r = client.get("/api/strategies")
    assert r.status_code == 403


def test_list_strategies_returns_user_rows():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="s1", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.get("/api/strategies")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    names = [s["name"] for s in body]
    assert "s1" in names


def test_list_strategies_excludes_other_users():
    _grant_permission_to_paul()
    # Another user's strategy must not appear.
    with get_connection() as conn:
        conn.execute("INSERT INTO users (name) VALUES ('alice')")
        conn.commit()
    create_strategy(user_id=2, name="alice_strategy", direction="long",
                    contract="TX", contract_size=1, **_good_dsls())

    sid_paul = create_strategy(user_id=1, name="paul_strategy",
                               direction="long", contract="TX",
                               contract_size=1, **_good_dsls())

    body = client.get("/api/strategies").json()
    names = [s["name"] for s in body]
    assert "paul_strategy" in names
    assert "alice_strategy" not in names


def test_get_one_strategy():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="short",
                          contract="MTX", contract_size=2, **_good_dsls())
    r = client.get(f"/api/strategies/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == sid
    assert body["direction"] == "short"
    assert body["contract"] == "MTX"
    assert body["entry_dsl"]["all"][0]["op"] == "gt"


def test_get_one_strategy_404_when_not_owned():
    _grant_permission_to_paul()
    with get_connection() as conn:
        conn.execute("INSERT INTO users (name) VALUES ('alice')")
        conn.commit()
    other = create_strategy(user_id=2, name="alice_only", direction="long",
                            contract="TX", contract_size=1, **_good_dsls())
    r = client.get(f"/api/strategies/{other}")
    assert r.status_code == 404


def test_get_signals_returns_newest_first():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="s", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    write_signal(sid, kind="ENTRY_SIGNAL", signal_date="2026-01-15",
                 close_at_signal=100.0)
    write_signal(sid, kind="EXIT_SIGNAL", signal_date="2026-01-22",
                 close_at_signal=120.0, exit_reason="TAKE_PROFIT")

    r = client.get(f"/api/strategies/{sid}/signals")
    assert r.status_code == 200
    body = r.json()
    assert [s["kind"] for s in body] == ["EXIT_SIGNAL", "ENTRY_SIGNAL"]


def test_get_dsl_schema_lists_all_indicators():
    _grant_permission_to_paul()
    r = client.get("/api/strategies/dsl/schema")
    assert r.status_code == 200
    body = r.json()
    indicator_names = [i["name"] for i in body["indicators"]]
    assert set(indicator_names) == {
        "sma", "ema", "rsi", "macd", "bbands", "atr", "kd",
        "highest", "lowest", "change_pct",
    }
    assert "cross_above" in body["operators"]
    assert "close" in body["fields"]


def test_dsl_schema_indicators_match_runtime_models():
    """Drift guard: every indicator in DSL_SCHEMA must round-trip through
    the Pydantic models."""
    _grant_permission_to_paul()
    body = client.get("/api/strategies/dsl/schema").json()
    from services.strategy_dsl.models import ExprNode
    for ind in body["indicators"]:
        d = {"indicator": ind["name"]}
        # Fill required params with defaults / minimums so validation passes.
        for p in ind["params"]:
            if "default" in p:
                d[p["name"]] = p["default"]
            elif p["type"] == "int":
                d[p["name"]] = p["min"]
            elif p["type"] == "float":
                d[p["name"]] = p["min"] or 1.0
        ExprNode.validate_python(d)
```

- [ ] **Step 4.2: Run — should fail because the route module doesn't exist**

```bash
python3 -m pytest tests/test_strategies_routes.py -v 2>&1 | tail -25
```

Expected: 404 on every endpoint (route file not registered yet).

- [ ] **Step 4.3: Create the route module skeleton**

Create `backend/api/routes/strategies.py`:

```python
"""HTTP API for the Futures Strategy Engine.

All endpoints sit behind require_strategy_permission so the user has
both a valid token AND can_use_strategy=True. Ownership is enforced per
endpoint by matching strategy.user_id to the request's user. A request
for someone else's strategy returns 404 (not 403) so id enumeration
can't distinguish "doesn't exist" from "not yours".
"""
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_strategy_permission
from api.schemas.strategy import (
    StrategyResponse, SignalResponse,
)
from api.strategy_dsl_schema import DSL_SCHEMA
from repositories.strategies import (
    get_strategy, list_signals,
)
from db.connection import get_connection


router = APIRouter(
    prefix="/api/strategies",
    tags=["strategies"],
    dependencies=[Depends(require_strategy_permission)],
)


def _list_user_strategies(user_id: int) -> list[dict]:
    """Read all strategies for a user (regardless of notify_enabled)."""
    import json as _json
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM strategies WHERE user_id=? ORDER BY id",
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["entry_dsl"] = _json.loads(d["entry_dsl"])
        d["take_profit_dsl"] = _json.loads(d["take_profit_dsl"])
        d["stop_loss_dsl"] = _json.loads(d["stop_loss_dsl"])
        d["notify_enabled"] = bool(d["notify_enabled"])
        out.append(d)
    return out


def _own_or_404(strategy_id: int, user: dict) -> dict:
    s = get_strategy(strategy_id)
    if s is None or s["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return s


@router.get("", response_model=list[StrategyResponse])
def list_strategies(user: dict = Depends(require_strategy_permission)):
    return _list_user_strategies(user["id"])


@router.get("/dsl/schema")
def get_dsl_schema(user: dict = Depends(require_strategy_permission)):
    return DSL_SCHEMA


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_one_strategy(strategy_id: int,
                     user: dict = Depends(require_strategy_permission)):
    return _own_or_404(strategy_id, user)


@router.get("/{strategy_id}/signals", response_model=list[SignalResponse])
def get_strategy_signals(strategy_id: int, limit: int = 50,
                          user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    return list_signals(strategy_id, limit=limit)
```

- [ ] **Step 4.4: Register the router**

In `backend/main.py`, find the imports block:

```python
from api.routes import indicators, stocks, fundamentals, news, futures, me
```

Replace with:

```python
from api.routes import (
    indicators, stocks, fundamentals, news, futures, me,
    strategies,
)
```

Then find the `app.include_router(me.router)` line and add immediately after:

```python
app.include_router(strategies.router)
```

- [ ] **Step 4.5: Run — most should pass; one 403 test needs the conftest tweak**

```bash
python3 -m pytest tests/test_strategies_routes.py -v 2>&1 | tail -25
```

Expected: 8 PASS. If `test_list_strategies_403_without_permission` fails because `_grant_permission_to_paul` was called by a previous test (DB state leaked), the autouse `reset_db` fixture should clear it; verify the test ordering. If 403 on the OTHER tests, it means the `_grant_permission_to_paul()` step is being undone — confirm `reset_db` runs before each test.

NOTE on route ordering: `/api/strategies/dsl/schema` MUST be declared before `/api/strategies/{strategy_id}` (FastAPI matches in declaration order — otherwise the literal "dsl" gets parsed as a strategy id and 422s). The route file above declares them in the correct order.

- [ ] **Step 4.6: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 428 PASS (420 + 8 new).

- [ ] **Step 4.7: Commit**

```bash
git add backend/api/routes/strategies.py backend/main.py tests/test_strategies_routes.py
git commit -m "$(cat <<'EOF'
feat(api): GET /api/strategies/* read endpoints

list / get-one / get-signals / dsl/schema. All routes gated by
require_strategy_permission. Ownership enforced via 404 on someone
else's strategy id (not 403, so the gate doesn't leak existence).

dsl/schema route returns the static DSL_SCHEMA dict the frontend
condition builder will read; a drift-guard test asserts every indicator
in the schema round-trips through the runtime Pydantic models.
EOF
)"
```

---

## Task 5 — Write endpoints + state actions

**Files:**
- Modify: `backend/api/routes/strategies.py`
- Modify: `backend/services/strategy_engine.py` (add `force_close`)
- Modify: `tests/test_strategies_routes.py`

POST / PATCH / DELETE for CRUD; enable / disable / force_close / reset for state actions. The DSL fields go through `validate(...)` with `check_translatability=True` on write so anything that schema-validates but Backtrader can't represent fails 422.

The `force_close` engine helper: writes EXIT_FILLED with `exit_reason='MANUAL_RESET'` using the latest bar's close as the assumed fill price (since there is no next-bar open available — the user is acting outside the daily cycle). Sends a notification.

- [ ] **Step 5.1: Append failing tests**

Append to `tests/test_strategies_routes.py`:

```python
def test_create_strategy_happy_path():
    _grant_permission_to_paul()
    body = {
        "name": "rsi_long",
        "direction": "long",
        "contract": "TX",
        "contract_size": 1,
        "max_hold_days": 10,
        **_good_dsls(),
    }
    r = client.post("/api/strategies", json=body)
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    assert new_id > 0
    # Round-trip check
    r2 = client.get(f"/api/strategies/{new_id}")
    assert r2.json()["name"] == "rsi_long"
    assert r2.json()["state"] == "idle"


def test_create_strategy_rejects_invalid_dsl():
    _grant_permission_to_paul()
    bad = {
        "name": "bad",
        "direction": "long",
        "contract": "TX",
        "contract_size": 1,
        "entry_dsl": {"version": 1, "all": [{"left": {"var": "entry_price"},
                                              "op": "gt", "right": {"const": 0}}]},
        "take_profit_dsl": {"version": 1, "type": "pct", "value": 2.0},
        "stop_loss_dsl":   {"version": 1, "type": "pct", "value": 1.0},
    }
    r = client.post("/api/strategies", json=bad)
    assert r.status_code == 422
    assert "entry_price" in r.text


def test_update_strategy_partial():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="orig", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.patch(f"/api/strategies/{sid}",
                     json={"name": "renamed", "contract_size": 3})
    assert r.status_code == 200
    after = client.get(f"/api/strategies/{sid}").json()
    assert after["name"] == "renamed"
    assert after["contract_size"] == 3


def test_update_strategy_in_position_freezes_dsl_fields():
    """Spec §9d3: when the strategy is currently in a hypothetical
    position (state != idle), DSL columns are read-only; only metadata
    (name, contract_size) can change."""
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="in_pos", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    from repositories.strategies import update_strategy_state
    update_strategy_state(sid, state="open",
                          entry_signal_date="2026-01-15",
                          entry_fill_date="2026-01-16",
                          entry_fill_price=200.0)

    r = client.patch(f"/api/strategies/{sid}",
                     json={"entry_dsl": _good_dsls()["entry_dsl"]})
    assert r.status_code == 422
    assert "in_position" in r.text or "in position" in r.text

    # Metadata-only update still allowed.
    r2 = client.patch(f"/api/strategies/{sid}",
                      json={"name": "still_renamable"})
    assert r2.status_code == 200


def test_delete_strategy_cascades_signals():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="del_me", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    write_signal(sid, kind="ENTRY_SIGNAL", signal_date="2026-01-15",
                 close_at_signal=100.0)

    r = client.delete(f"/api/strategies/{sid}")
    assert r.status_code == 200
    r2 = client.get(f"/api/strategies/{sid}")
    assert r2.status_code == 404


def test_enable_requires_webhook_set():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.post(f"/api/strategies/{sid}/enable")
    assert r.status_code == 422
    assert "webhook" in r.text


def test_enable_passes_when_webhook_set():
    _grant_permission_to_paul()
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET discord_webhook_url=? WHERE id=1",
            ("https://discord.com/api/webhooks/1/" + "x" * 60,),
        )
        conn.commit()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.post(f"/api/strategies/{sid}/enable")
    assert r.status_code == 200
    after = client.get(f"/api/strategies/{sid}").json()
    assert after["notify_enabled"] is True


def test_disable_route():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1,
                          notify_enabled=True, **_good_dsls())
    r = client.post(f"/api/strategies/{sid}/disable")
    assert r.status_code == 200
    after = client.get(f"/api/strategies/{sid}").json()
    assert after["notify_enabled"] is False


def test_force_close_only_when_in_position():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.post(f"/api/strategies/{sid}/force_close")
    assert r.status_code == 422
    assert "not in position" in r.text or "state" in r.text


def test_force_close_writes_exit_filled_manual_reset():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    # Fake an open position via direct state update.
    from repositories.strategies import update_strategy_state
    from repositories.futures import save_futures_daily_rows
    update_strategy_state(sid, state="open",
                          entry_signal_date="2026-01-15",
                          entry_fill_date="2026-01-16",
                          entry_fill_price=200.0)
    save_futures_daily_rows([{
        "symbol": "TX", "date": "2026-01-25", "contract_date": "202604",
        "open": 210.0, "high": 215.0, "low": 209.0, "close": 212.0,
        "volume": 1000, "open_interest": None, "settlement": None,
    }])

    r = client.post(f"/api/strategies/{sid}/force_close")
    assert r.status_code == 200

    after = client.get(f"/api/strategies/{sid}").json()
    assert after["state"] == "idle"

    sigs = client.get(f"/api/strategies/{sid}/signals").json()
    assert sigs[0]["kind"] == "EXIT_FILLED"
    assert sigs[0]["exit_reason"] == "MANUAL_RESET"


def test_reset_strategy_clears_all():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    write_signal(sid, kind="ENTRY_SIGNAL", signal_date="2026-01-15",
                 close_at_signal=200.0)
    from repositories.strategies import mark_strategy_error
    mark_strategy_error(sid, "boom")

    r = client.post(f"/api/strategies/{sid}/reset")
    assert r.status_code == 200

    after = client.get(f"/api/strategies/{sid}").json()
    assert after["state"] == "idle"
    assert after["last_error"] is None
    sigs = client.get(f"/api/strategies/{sid}/signals").json()
    assert sigs == []
```

- [ ] **Step 5.2: Run — every new test should fail (route methods missing)**

```bash
python3 -m pytest tests/test_strategies_routes.py -v 2>&1 | tail -30
```

Expected: 11 fails (405 / 404) on the new endpoints.

- [ ] **Step 5.3: Add `force_close` to the engine**

Append to `backend/services/strategy_engine.py`:

```python
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
            f"(state={strategy['state']!r})"
        )
    rows = get_futures_daily_range(strategy["contract"], "1900-01-01")
    if not rows:
        raise ValueError(
            f"no bars in futures_daily for contract={strategy['contract']!r}"
        )
    last_bar = rows[-1]
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
    notify_signal(strategy, "EXIT_FILLED", last_bar)
```

- [ ] **Step 5.4: Implement the write + state-action endpoints**

Replace the imports + body of `backend/api/routes/strategies.py` to add the new endpoints. The file becomes:

```python
"""HTTP API for the Futures Strategy Engine.

All endpoints sit behind require_strategy_permission. Ownership enforced
via 404. DSL bodies on write go through services.strategy_dsl.validator
.validate(check_translatability=True) so anything Backtrader can't
represent fails 422 before it hits the DB.
"""
import json as _json

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_strategy_permission
from api.schemas.strategy import (
    StrategyCreate, StrategyUpdate, StrategyResponse, SignalResponse,
)
from api.strategy_dsl_schema import DSL_SCHEMA
from repositories.strategies import (
    get_strategy, list_signals, create_strategy, update_strategy,
    delete_strategy, reset_strategy,
)
from services.strategy_dsl.validator import validate, DSLValidationError
from services.strategy_engine import force_close
from db.connection import get_connection


router = APIRouter(
    prefix="/api/strategies",
    tags=["strategies"],
    dependencies=[Depends(require_strategy_permission)],
)


def _list_user_strategies(user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM strategies WHERE user_id=? ORDER BY id",
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["entry_dsl"] = _json.loads(d["entry_dsl"])
        d["take_profit_dsl"] = _json.loads(d["take_profit_dsl"])
        d["stop_loss_dsl"] = _json.loads(d["stop_loss_dsl"])
        d["notify_enabled"] = bool(d["notify_enabled"])
        out.append(d)
    return out


def _own_or_404(strategy_id: int, user: dict) -> dict:
    s = get_strategy(strategy_id)
    if s is None or s["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return s


def _validate_dsls(entry_dsl, take_profit_dsl, stop_loss_dsl) -> None:
    try:
        validate(entry_dsl, kind="entry", check_translatability=True)
        validate(take_profit_dsl, kind="take_profit", check_translatability=True)
        validate(stop_loss_dsl, kind="stop_loss", check_translatability=True)
    except DSLValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── read endpoints (Task 4) ─────────────────────────────────────────

@router.get("", response_model=list[StrategyResponse])
def list_strategies(user: dict = Depends(require_strategy_permission)):
    return _list_user_strategies(user["id"])


@router.get("/dsl/schema")
def get_dsl_schema(user: dict = Depends(require_strategy_permission)):
    return DSL_SCHEMA


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_one_strategy(strategy_id: int,
                     user: dict = Depends(require_strategy_permission)):
    return _own_or_404(strategy_id, user)


@router.get("/{strategy_id}/signals", response_model=list[SignalResponse])
def get_strategy_signals(strategy_id: int, limit: int = 50,
                          user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    return list_signals(strategy_id, limit=limit)


# ── write endpoints (Task 5) ────────────────────────────────────────

@router.post("")
def create_strategy_route(req: StrategyCreate,
                          user: dict = Depends(require_strategy_permission)):
    _validate_dsls(req.entry_dsl, req.take_profit_dsl, req.stop_loss_dsl)
    try:
        new_id = create_strategy(
            user_id=user["id"],
            name=req.name,
            direction=req.direction,
            contract=req.contract,
            contract_size=req.contract_size,
            max_hold_days=req.max_hold_days,
            entry_dsl=req.entry_dsl,
            take_profit_dsl=req.take_profit_dsl,
            stop_loss_dsl=req.stop_loss_dsl,
            notify_enabled=False,
        )
    except Exception as e:
        # Most likely UNIQUE(user_id, name) collision.
        raise HTTPException(status_code=409, detail=f"create failed: {e}")
    return {"id": new_id}


@router.patch("/{strategy_id}")
def update_strategy_route(strategy_id: int, req: StrategyUpdate,
                          user: dict = Depends(require_strategy_permission)):
    s = _own_or_404(strategy_id, user)
    fields = req.model_dump(exclude_unset=True)
    if not fields:
        return {"ok": True}

    in_position = s["state"] != "idle"
    dsl_keys = {"entry_dsl", "take_profit_dsl", "stop_loss_dsl",
                "direction", "contract", "max_hold_days"}
    if in_position and (set(fields) & dsl_keys):
        raise HTTPException(
            status_code=422,
            detail=("strategy is in_position; only metadata "
                    "(name / contract_size) can be edited until reset"),
        )

    if any(k in fields for k in ("entry_dsl", "take_profit_dsl", "stop_loss_dsl")):
        _validate_dsls(
            fields.get("entry_dsl",       s["entry_dsl"]),
            fields.get("take_profit_dsl", s["take_profit_dsl"]),
            fields.get("stop_loss_dsl",   s["stop_loss_dsl"]),
        )

    update_strategy(strategy_id, **fields)
    return {"ok": True}


@router.delete("/{strategy_id}")
def delete_strategy_route(strategy_id: int,
                          user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    delete_strategy(strategy_id)
    return {"ok": True}


# ── state actions ───────────────────────────────────────────────────

@router.post("/{strategy_id}/enable")
def enable_strategy(strategy_id: int,
                    user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    if not user.get("discord_webhook_url"):
        raise HTTPException(
            status_code=422,
            detail="discord webhook not set for user; ask admin to set one",
        )
    update_strategy(strategy_id, notify_enabled=True)
    return {"ok": True}


@router.post("/{strategy_id}/disable")
def disable_strategy(strategy_id: int,
                     user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    update_strategy(strategy_id, notify_enabled=False)
    return {"ok": True}


@router.post("/{strategy_id}/force_close")
def force_close_strategy(strategy_id: int,
                          user: dict = Depends(require_strategy_permission)):
    s = _own_or_404(strategy_id, user)
    try:
        force_close(s)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.post("/{strategy_id}/reset")
def reset_strategy_route(strategy_id: int,
                          user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    reset_strategy(strategy_id)
    return {"ok": True}
```

- [ ] **Step 5.5: Run — should pass**

```bash
python3 -m pytest tests/test_strategies_routes.py -v 2>&1 | tail -30
```

Expected: 19 PASS (8 from Task 4 + 11 new).

- [ ] **Step 5.6: Run engine tests too**

```bash
python3 -m pytest tests/test_strategy_engine.py -v 2>&1 | tail -15
```

Expected: 9 PASS (force_close has its own coverage via the route test).

- [ ] **Step 5.7: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 439 PASS (428 + 11 new).

- [ ] **Step 5.8: Commit**

```bash
git add backend/api/routes/strategies.py backend/services/strategy_engine.py tests/test_strategies_routes.py
git commit -m "$(cat <<'EOF'
feat(api): write + state-action endpoints for /api/strategies/*

POST create / PATCH update (DSL frozen while in_position) / DELETE
(cascade signals) / enable (422 without webhook) / disable / force_close
(EXIT_FILLED with reason=MANUAL_RESET on the latest bar's close) /
reset (drop signals + clear state machine).

Engine gains force_close(strategy) which validates state ∈
{open,pending_exit} and writes a manual-close trade row, sending
notify_signal so the user sees the close land in their Discord.

All write paths run validate(check_translatability=True) so any DSL
that schema-validates but Backtrader can't represent is rejected with
422 before hitting the DB.
EOF
)"
```

---

## Task 6 — Backtest endpoint

**Files:**
- Modify: `backend/services/strategy_backtest.py` (add `run_backtest_from_db`)
- Modify: `backend/api/routes/strategies.py` (add POST `/{id}/backtest`)
- Modify: `tests/test_strategies_routes.py` (add backtest tests)
- Modify: `tests/strategies/test_backtest.py` (add unit test for `run_backtest_from_db`)

Backtest is the largest single endpoint. It loads bars from `futures_daily` for the requested date range, calls the existing P2 `run_backtest`, and serialises the result into the `BacktestResponse` shape from Task 2.

- [ ] **Step 6.1: Write the failing tests**

Append to `tests/strategies/test_backtest.py`:

```python
def test_run_backtest_from_db_pulls_bars_and_runs(make_strategy):
    """Synthetic bars in futures_daily → end-to-end backtest result."""
    from repositories.futures import save_futures_daily_rows
    from services.strategy_backtest import run_backtest_from_db

    import datetime
    base = datetime.date(2026, 1, 1)
    rows = []
    for i in range(60):
        rows.append({
            "symbol": "TX",
            "date":   str(base + datetime.timedelta(days=i)),
            "contract_date": "202604",
            "open":   100.0 + i,
            "high":   100.0 + i + 2,
            "low":    100.0 + i - 2,
            "close":  100.0 + i,
            "volume": 1000,
            "open_interest": None, "settlement": None,
        })
    save_futures_daily_rows(rows)

    s = make_strategy(entry={
        "version": 1,
        "all": [{"left": {"field": "close"}, "op": "gt",
                 "right": {"const": 0}}],
    })
    res = run_backtest_from_db(s,
                               start_date="2026-01-01",
                               end_date="2026-02-28")
    assert res.summary.n_trades >= 1
```

Append to `tests/test_strategies_routes.py`:

```python
def test_backtest_endpoint_round_trip():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="bt", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())

    # Seed enough bars for the engine to produce a trade.
    from repositories.futures import save_futures_daily_rows
    import datetime
    base = datetime.date(2026, 1, 1)
    rows = []
    for i in range(80):
        rows.append({
            "symbol": "TX",
            "date":   str(base + datetime.timedelta(days=i)),
            "contract_date": "202604",
            "open":   100.0 + i,
            "high":   100.0 + i + 2,
            "low":    100.0 + i - 2,
            "close":  100.0 + i,
            "volume": 1000,
            "open_interest": None, "settlement": None,
        })
    save_futures_daily_rows(rows)

    r = client.post(f"/api/strategies/{sid}/backtest", json={
        "start_date": "2026-01-01",
        "end_date":   "2026-03-21",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "trades" in body
    assert "summary" in body
    assert body["summary"]["n_trades"] == len(body["trades"])


def test_backtest_endpoint_404_for_other_user():
    _grant_permission_to_paul()
    with get_connection() as conn:
        conn.execute("INSERT INTO users (name) VALUES ('alice')")
        conn.commit()
    other = create_strategy(user_id=2, name="alice_only", direction="long",
                            contract="TX", contract_size=1, **_good_dsls())
    r = client.post(f"/api/strategies/{other}/backtest", json={
        "start_date": "2026-01-01", "end_date": "2026-02-01",
    })
    assert r.status_code == 404


def test_backtest_endpoint_returns_warning_on_no_bars():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="empty_bt", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.post(f"/api/strategies/{sid}/backtest", json={
        "start_date": "2026-01-01", "end_date": "2026-02-01",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["trades"] == []
    assert body["summary"]["n_trades"] == 0
    assert any("no bars" in w.lower() for w in body["warnings"])
```

- [ ] **Step 6.2: Run — should fail**

```bash
python3 -m pytest tests/strategies/test_backtest.py tests/test_strategies_routes.py -v 2>&1 | tail -25
```

Expected: 4 fails (`run_backtest_from_db` missing + endpoint 404 / 405).

- [ ] **Step 6.3: Add `run_backtest_from_db` to `strategy_backtest.py`**

Append to `backend/services/strategy_backtest.py`:

```python
def run_backtest_from_db(
    strategy,
    *,
    start_date: str,
    end_date: str,
    contract_override: str | None = None,
    contract_size_override: int | None = None,
) -> BacktestResult:
    """Load bars from futures_daily for the requested range + contract,
    then call run_backtest. Returns an empty BacktestResult with a warning
    if no bars are present in the range."""
    from repositories.futures import get_futures_daily_range

    contract = contract_override or strategy.contract
    rows = get_futures_daily_range(contract, start_date)
    bars = [
        {"date": r["date"],
         "open": r["open"], "high": r["high"], "low": r["low"],
         "close": r["close"], "volume": r["volume"]}
        for r in rows
        if start_date <= r["date"] <= end_date
    ]
    if not bars:
        empty = BacktestResult(
            trades=[],
            summary=Summary(
                total_pnl_amount=0.0, win_rate=0.0,
                avg_win_points=0.0, avg_loss_points=0.0,
                profit_factor=0.0, max_drawdown_amt=0.0,
                max_drawdown_pct=0.0, n_trades=0, avg_held_bars=0.0,
            ),
        )
        empty.warnings.append(
            f"no bars in futures_daily for contract={contract} "
            f"between {start_date} and {end_date}"
        )
        return empty

    if contract_size_override is not None:
        # Mutate a shallow copy so the caller's strategy stays untouched.
        from dataclasses import replace
        strategy = replace(strategy, contract_size=contract_size_override)
    return run_backtest(strategy, bars=bars)
```

- [ ] **Step 6.4: Add the backtest endpoint**

Insert into `backend/api/routes/strategies.py` (right before `# ── state actions`):

```python
from api.schemas.strategy import (
    BacktestRequest, BacktestResponse, TradeOut, SummaryOut,
)
from services.strategy_backtest import run_backtest_from_db
from dataclasses import dataclass


@dataclass
class _StrategyForBacktest:
    """Adapter that gives services.strategy_backtest.try_translate the
    fields it expects without depending on a route-layer dataclass."""
    direction: str
    contract: str
    contract_size: int
    max_hold_days: int | None
    entry_dsl: dict
    take_profit_dsl: dict
    stop_loss_dsl: dict


@router.post("/{strategy_id}/backtest", response_model=BacktestResponse)
def backtest_strategy(strategy_id: int, req: BacktestRequest,
                      user: dict = Depends(require_strategy_permission)):
    s = _own_or_404(strategy_id, user)
    adapter = _StrategyForBacktest(
        direction=s["direction"],
        contract=s["contract"],
        contract_size=s["contract_size"],
        max_hold_days=s["max_hold_days"],
        entry_dsl=s["entry_dsl"],
        take_profit_dsl=s["take_profit_dsl"],
        stop_loss_dsl=s["stop_loss_dsl"],
    )
    result = run_backtest_from_db(
        adapter,
        start_date=str(req.start_date),
        end_date=str(req.end_date),
        contract_override=req.contract,
        contract_size_override=req.contract_size,
    )
    return BacktestResponse(
        trades=[
            TradeOut(
                entry_date=str(t.entry_date),
                entry_price=t.entry_price,
                exit_date=str(t.exit_date),
                exit_price=t.exit_price,
                exit_reason=t.exit_reason,
                held_bars=t.held_bars,
                pnl_points=t.pnl_points,
                pnl_amount=t.pnl_amount,
                from_stop=t.from_stop,
            )
            for t in result.trades
        ],
        summary=SummaryOut(**vars(result.summary)),
        warnings=result.warnings,
    )
```

- [ ] **Step 6.5: Run — should pass**

```bash
python3 -m pytest tests/strategies/test_backtest.py tests/test_strategies_routes.py -v 2>&1 | tail -30
```

Expected: 26 PASS (7 from P2 + 19 routes + 3 new).

- [ ] **Step 6.6: Full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 443 PASS (439 + 4 new — 3 routes + 1 service test).

- [ ] **Step 6.7: Commit**

```bash
git add backend/services/strategy_backtest.py backend/api/routes/strategies.py tests/strategies/test_backtest.py tests/test_strategies_routes.py
git commit -m "$(cat <<'EOF'
feat(api): POST /api/strategies/{id}/backtest

run_backtest_from_db loads bars from futures_daily for the requested
range + contract and delegates to the existing P2 run_backtest. Returns
an empty BacktestResult with a warning when no bars cover the range so
the frontend can show "no data" instead of erroring.

Route adapter shapes the strategy dict into the dataclass-like object
strategy_backtest.try_translate expects, then maps the result into the
typed BacktestResponse. contract / contract_size overrides on the
request body let users try the same DSL on MTX/TMF without forking the
strategy.
EOF
)"
```

---

## Task 7 — Real notifier (Discord embeds)

**Files:**
- Modify: `backend/services/strategy_notifier.py`
- Create: `tests/test_strategy_notifier_real.py`
- Modify: `tests/test_strategy_notifier.py` (rename or delete the obsolete log-only tests; keep one regression that asserts the no-webhook path silently succeeds)

The notifier swaps log-only bodies for `core.discord.send_to_discord(webhook_url, payload)` calls. Spec §7.3 specifies the embed shapes. Runtime errors fan out to two webhooks (user + ops global).

- [ ] **Step 7.1: Replace the log-only tests with a real-Discord test file**

Delete `tests/test_strategy_notifier.py` and create `tests/test_strategy_notifier_real.py`:

```python
"""Tests for the real Discord notifier — patches send_to_discord to
capture payloads and assert embed structure."""
from unittest.mock import patch

from db.connection import get_connection
from services.strategy_notifier import (
    notify_signal, notify_runtime_error,
)


def _set_paul_webhook(url: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET discord_webhook_url=? WHERE id=1",
            (url,),
        )
        conn.commit()


def test_notify_signal_no_webhook_silently_skips():
    """A user without a webhook still has signals written to DB; we just
    don't post anywhere. Logs a warning."""
    _set_paul_webhook(None)
    strategy = {"id": 1, "user_id": 1,
                "name": "s", "contract": "TX", "direction": "long"}
    today_bar = {"date": "2026-05-15", "close": 17250.0}
    with patch("services.strategy_notifier.send_to_discord") as mock_post:
        notify_signal(strategy, "ENTRY_SIGNAL", today_bar)
        mock_post.assert_not_called()


def test_notify_entry_signal_posts_embed_to_user_webhook():
    url = "https://discord.com/api/webhooks/1/" + "x" * 60
    _set_paul_webhook(url)
    strategy = {"id": 42, "user_id": 1, "name": "rsi_long",
                "contract": "TX", "direction": "long"}
    today_bar = {"date": "2026-05-15", "close": 17250.0}

    with patch("services.strategy_notifier.send_to_discord") as mock_post:
        notify_signal(strategy, "ENTRY_SIGNAL", today_bar)

    assert mock_post.call_count == 1
    args, kwargs = mock_post.call_args
    sent_url, payload = args[0], args[1]
    assert sent_url == url
    assert "embeds" in payload
    embed = payload["embeds"][0]
    assert "📈" in embed["title"]
    assert "rsi_long" in embed["title"]
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    # The fields should describe direction/contract/lots and the current bar.
    assert "TX" in fields.get("方向 / 商品 / 口數", "")
    assert "17,250" in fields.get("訊號當日 close", "") or "17250" in fields.get("訊號當日 close", "")


def test_notify_exit_signal_take_profit_uses_green_color():
    url = "https://discord.com/api/webhooks/1/" + "x" * 60
    _set_paul_webhook(url)
    strategy = {"id": 5, "user_id": 1, "name": "x",
                "contract": "TX", "direction": "long",
                "entry_fill_price": 200.0,
                "entry_fill_date":  "2026-05-10",
                "pending_exit_kind": "TAKE_PROFIT"}
    today_bar = {"date": "2026-05-15", "close": 210.0}

    with patch("services.strategy_notifier.send_to_discord") as mock_post:
        notify_signal(strategy, "EXIT_SIGNAL", today_bar)

    payload = mock_post.call_args.args[1]
    embed = payload["embeds"][0]
    # Spec §7.3 mapping: TAKE_PROFIT → 0x2ECC71 (green)
    assert embed["color"] == 0x2ECC71
    assert "💰" in embed["title"]


def test_notify_runtime_error_posts_to_both_user_and_ops(monkeypatch):
    url = "https://discord.com/api/webhooks/1/" + "x" * 60
    _set_paul_webhook(url)
    # Stub the global ops webhook setting.
    from core.settings import settings
    monkeypatch.setattr(
        settings, "discord_ops_webhook_url",
        type("S", (), {"get_secret_value": lambda self: "https://ops/" + "y" * 60})(),
        raising=False,
    )

    strategy = {"id": 9, "user_id": 1, "name": "x",
                "contract": "TX", "direction": "long"}
    err = ValueError("DSL exploded")

    with patch("services.strategy_notifier.send_to_discord") as mock_post:
        notify_runtime_error(strategy, err)

    sent_urls = [c.args[0] for c in mock_post.call_args_list]
    assert url in sent_urls
    assert "ops" in str(sent_urls)


def test_notify_runtime_error_no_user_webhook_still_posts_to_ops(monkeypatch):
    _set_paul_webhook(None)
    from core.settings import settings
    monkeypatch.setattr(
        settings, "discord_ops_webhook_url",
        type("S", (), {"get_secret_value": lambda self: "https://ops/" + "y" * 60})(),
        raising=False,
    )

    strategy = {"id": 9, "user_id": 1, "name": "x",
                "contract": "TX", "direction": "long"}
    err = RuntimeError("kaboom")

    with patch("services.strategy_notifier.send_to_discord") as mock_post:
        notify_runtime_error(strategy, err)

    sent_urls = [c.args[0] for c in mock_post.call_args_list]
    # User has no webhook → only ops gets the post.
    assert len(sent_urls) == 1
    assert "ops" in sent_urls[0]


def test_notify_signal_swallows_discord_failure(caplog):
    """If Discord rejects the post, the engine call must NOT raise — the
    error is logged and we move on so other strategies still evaluate."""
    import logging
    url = "https://discord.com/api/webhooks/1/" + "x" * 60
    _set_paul_webhook(url)
    strategy = {"id": 1, "user_id": 1, "name": "s",
                "contract": "TX", "direction": "long"}
    today_bar = {"date": "2026-05-15", "close": 17250.0}

    def boom(*a, **kw):
        raise RuntimeError("Discord 503")

    with patch("services.strategy_notifier.send_to_discord", side_effect=boom):
        with caplog.at_level(logging.WARNING):
            notify_signal(strategy, "ENTRY_SIGNAL", today_bar)

    assert "503" in caplog.text or "discord" in caplog.text.lower()
```

- [ ] **Step 7.2: Run — should fail**

```bash
python3 -m pytest tests/test_strategy_notifier_real.py -v 2>&1 | tail -20
```

Expected: tests fail because (a) the old notifier is log-only, doesn't import send_to_discord; (b) the test_strategy_notifier.py file might still exist and import old stub names. If the old test file is still around, delete it via `rm tests/test_strategy_notifier.py`.

- [ ] **Step 7.3: Replace `services/strategy_notifier.py` with the real implementation**

```python
"""Strategy notifier — Discord webhook poster.

Two surfaces:
  - notify_signal(strategy, kind, today_bar): per-user webhook only.
    No fallback — if the user has no webhook configured, we silently
    skip (the engine still writes the signal row, so the frontend
    history shows it).
  - notify_runtime_error(strategy, error): dual fan-out. Posts to the
    user's webhook (if set) AND the ops global webhook
    (settings.discord_ops_webhook_url). The ops post is the operator's
    monitoring surface; the user post lets them know their strategy
    is broken.

Both swallow Discord failures so a flaky webhook can't take down the
fetcher path.
"""
import logging
from typing import Optional

from core.discord import send_to_discord
from core.settings import settings
from repositories.users import get_user_with_settings


logger = logging.getLogger(__name__)


# ── embed builders ──────────────────────────────────────────────────

_ENTRY_TITLE = "📈 進場訊號"
_EXIT_TITLES = {
    "TAKE_PROFIT":  ("💰 停利訊號", 0x2ECC71),
    "STOP_LOSS":    ("🛑 停損訊號", 0xE67E22),
    "TIMEOUT":      ("⏰ 持倉到期",  0x95A5A6),
    "MANUAL_RESET": ("🔧 手動平倉", 0x95A5A6),
}


def _format_close(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def _build_signal_payload(strategy: dict, kind: str, today_bar: dict) -> dict:
    name = strategy.get("name", "(unnamed)")
    direction = strategy.get("direction", "")
    contract = strategy.get("contract", "")
    size = strategy.get("contract_size", 1)
    close = today_bar.get("close")
    date = today_bar.get("date", "")

    direction_text = "多" if direction == "long" else "空"
    fields = [
        {"name": "方向 / 商品 / 口數",
         "value": f"{direction_text} / {contract} / {size}",
         "inline": True},
        {"name": "訊號當日 close",
         "value": _format_close(close),
         "inline": True},
    ]

    if kind == "ENTRY_SIGNAL":
        title = f"{_ENTRY_TITLE} — {name}"
        color = 0xE74C3C if direction == "long" else 0x16A085
        description = "策略觸發進場條件，**明日 open 假想進場**。"
    else:
        # EXIT_SIGNAL or EXIT_FILLED (manual close).
        reason = strategy.get("pending_exit_kind") or "MANUAL_RESET"
        icon_title, color = _EXIT_TITLES.get(reason, ("⚠️ 出場", 0x95A5A6))
        title = f"{icon_title} — {name}"
        description = "**明日 open 假想出場**（手動平倉用最新 close 結算）。"
        entry_price = strategy.get("entry_fill_price")
        if entry_price is not None and close is not None:
            if direction == "long":
                pnl = close - entry_price
            else:
                pnl = entry_price - close
            fields.append({
                "name": "預估 PnL（以當日 close 估算）",
                "value": f"{pnl:+,.2f} 點",
                "inline": True,
            })
        if strategy.get("entry_fill_date"):
            fields.append({
                "name": "進場價 / 進場日",
                "value": f"{_format_close(entry_price)} @ {strategy['entry_fill_date']}",
                "inline": True,
            })

    return {
        "embeds": [{
            "title":       title,
            "description": description,
            "color":       color,
            "fields":      fields,
            "footer":      {"text": f"Strategy #{strategy.get('id')} · {date}"},
        }]
    }


def _build_runtime_error_embed(strategy: dict, error: Exception, *,
                               audience: str) -> dict:
    name = strategy.get("name", "(unnamed)")
    msg = str(error)[:600]
    if audience == "user":
        description = (
            f"您的策略 **{name}** 發生錯誤、即時通知已暫停。"
            f"請檢查條件後重新啟用。\n\n`{msg}`"
        )
    else:
        description = (
            f"strategy_id={strategy.get('id')} "
            f"user_id={strategy.get('user_id')} "
            f"name={name!r} contract={strategy.get('contract')!r}\n\n"
            f"```\n{msg}\n```"
        )
    return {
        "embeds": [{
            "title":       "⚠️ 策略執行錯誤",
            "description": description,
            "color":       0xE74C3C,
        }]
    }


# ── public functions ────────────────────────────────────────────────

def notify_signal(strategy: dict, kind: str, today_bar: dict) -> None:
    """Post a Discord embed for ENTRY_SIGNAL / EXIT_SIGNAL / EXIT_FILLED.
    Silently skips if the user has no webhook configured."""
    user = get_user_with_settings(strategy["user_id"])
    webhook = (user or {}).get("discord_webhook_url")
    if not webhook:
        logger.warning(
            "strategy_notify_skip_no_webhook strategy_id=%s user_id=%s",
            strategy.get("id"), strategy.get("user_id"),
        )
        return
    payload = _build_signal_payload(strategy, kind, today_bar)
    try:
        send_to_discord(webhook, payload)
    except Exception as e:
        logger.warning(
            "strategy_notify_discord_failed strategy_id=%s err=%s",
            strategy.get("id"), str(e)[:200],
        )


def notify_runtime_error(strategy: dict, error: Exception) -> None:
    """Dual fan-out: post to the user's webhook (if configured) AND the
    ops global webhook (settings.discord_ops_webhook_url)."""
    user = get_user_with_settings(strategy["user_id"])
    user_webhook = (user or {}).get("discord_webhook_url")
    if user_webhook:
        try:
            send_to_discord(
                user_webhook,
                _build_runtime_error_embed(strategy, error, audience="user"),
            )
        except Exception as e:
            logger.warning(
                "strategy_notify_user_err_failed strategy_id=%s err=%s",
                strategy.get("id"), str(e)[:200],
            )

    ops_secret = getattr(settings, "discord_ops_webhook_url", None)
    if ops_secret is not None:
        ops_url = ops_secret.get_secret_value() if hasattr(ops_secret, "get_secret_value") else str(ops_secret)
        if ops_url:
            try:
                send_to_discord(
                    ops_url,
                    _build_runtime_error_embed(strategy, error, audience="ops"),
                )
            except Exception as e:
                logger.warning(
                    "strategy_notify_ops_err_failed strategy_id=%s err=%s",
                    strategy.get("id"), str(e)[:200],
                )
```

- [ ] **Step 7.4: Delete the obsolete log-only test file**

```bash
rm /Users/paulwu/Documents/Github/publixia/tests/test_strategy_notifier.py
```

- [ ] **Step 7.5: Run notifier tests — should pass**

```bash
python3 -m pytest tests/test_strategy_notifier_real.py -v 2>&1 | tail -20
```

Expected: 6 tests PASS.

- [ ] **Step 7.6: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 446 PASS (443 + 6 new − 3 deleted log-only tests).

- [ ] **Step 7.7: Commit**

```bash
git add backend/services/strategy_notifier.py tests/test_strategy_notifier_real.py
git rm tests/test_strategy_notifier.py
git commit -m "$(cat <<'EOF'
feat(strategy): real Discord notifier replacing P3 log-only stubs

notify_signal posts a per-user-webhook embed for ENTRY_SIGNAL /
EXIT_SIGNAL / manually-closed EXIT_FILLED. Spec §7.3 colour table
applied (TAKE_PROFIT=green, STOP_LOSS=orange, TIMEOUT=grey,
MANUAL_RESET=grey, ENTRY long=red, ENTRY short=teal). No webhook
configured → silently skip; signal row is still written.

notify_runtime_error fans out to user webhook (if any) AND ops global
webhook (settings.discord_ops_webhook_url). Both posts are independently
try/except'd so one channel's flake doesn't block the other.

All Discord errors are swallowed + logged so the engine's daily
fetcher loop can never be taken down by a webhook outage.
EOF
)"
```

---

## Task 8 — Admin webhook test-message + cascade-disable

**Files:**
- Modify: `admin/ops.py`
- Modify: `admin/__main__.py`
- Create: `tests/test_admin_webhook_test_message.py`

`set_discord_webhook` becomes a two-step operation: persist the URL, then immediately POST a small test embed. If the test fails, roll back the persist. CLI surfaces the result.

`clear_discord_webhook` gains a sister function `clear_discord_webhook_with_cascade(user_id, *, also_disable_strategies)` that returns the list of currently-enabled strategy ids and optionally disables them.

- [ ] **Step 8.1: Write the failing tests**

Create `tests/test_admin_webhook_test_message.py`:

```python
"""Tests for admin webhook lifecycle: test-ping on set, cascade-disable on clear."""
from unittest.mock import patch

import pytest

from db.connection import get_connection
from admin import ops


def _good_url() -> str:
    return "https://discord.com/api/webhooks/1/" + "x" * 60


def test_set_webhook_pings_discord_and_persists_on_success():
    with patch("admin.ops.send_to_discord") as mock_post:
        result = ops.set_discord_webhook(1, _good_url())

    assert result.persisted is True
    assert result.test_ping_sent is True
    mock_post.assert_called_once()
    args = mock_post.call_args.args
    assert args[0] == _good_url()
    assert "embeds" in args[1]    # we sent an embed payload, not plain text


def test_set_webhook_rolls_back_on_test_ping_failure():
    """If Discord rejects the test post, persist is undone."""
    bad_url = "https://discord.com/api/webhooks/1/" + "y" * 60

    with patch("admin.ops.send_to_discord", side_effect=RuntimeError("404")):
        with pytest.raises(ValueError, match="test ping"):
            ops.set_discord_webhook(1, bad_url)

    rows = ops.list_users_with_token()
    paul = next(u for u in rows if u["id"] == 1)
    assert paul["webhook_display"] == "—"


def test_set_webhook_validation_runs_before_ping():
    with patch("admin.ops.send_to_discord") as mock_post:
        with pytest.raises(ValueError, match="discord webhook"):
            ops.set_discord_webhook(1, "not-a-discord-url")
        mock_post.assert_not_called()


def test_clear_with_cascade_lists_active_strategies():
    """If the user has notify_enabled strategies, list them; optionally
    disable in the same call."""
    from repositories.strategies import create_strategy
    sid = create_strategy(
        user_id=1, name="active", direction="long", contract="TX",
        contract_size=1,
        entry_dsl={"version": 1, "all": [
            {"left": {"field": "close"}, "op": "gt", "right": {"const": 0}}]},
        take_profit_dsl={"version": 1, "type": "pct", "value": 1.0},
        stop_loss_dsl  ={"version": 1, "type": "pct", "value": 1.0},
        notify_enabled=True,
    )
    affected = ops.clear_discord_webhook_with_cascade(
        1, also_disable_strategies=False,
    )
    assert sid in affected
    # The strategy is NOT disabled when the flag is False — only listed.
    from repositories.strategies import get_strategy
    assert get_strategy(sid)["notify_enabled"] is True


def test_clear_with_cascade_disables_when_requested():
    from repositories.strategies import create_strategy, get_strategy
    sid = create_strategy(
        user_id=1, name="active", direction="long", contract="TX",
        contract_size=1,
        entry_dsl={"version": 1, "all": [
            {"left": {"field": "close"}, "op": "gt", "right": {"const": 0}}]},
        take_profit_dsl={"version": 1, "type": "pct", "value": 1.0},
        stop_loss_dsl  ={"version": 1, "type": "pct", "value": 1.0},
        notify_enabled=True,
    )
    affected = ops.clear_discord_webhook_with_cascade(
        1, also_disable_strategies=True,
    )
    assert sid in affected
    assert get_strategy(sid)["notify_enabled"] is False
```

- [ ] **Step 8.2: Run — should fail**

```bash
python3 -m pytest tests/test_admin_webhook_test_message.py -v 2>&1 | tail -20
```

Expected: ImportError on `admin.ops.send_to_discord` and `clear_discord_webhook_with_cascade`.

- [ ] **Step 8.3: Update `admin/ops.py`**

Replace the existing `set_discord_webhook` body and append `clear_discord_webhook_with_cascade`. Open `admin/ops.py`, find:

```python
def set_discord_webhook(user_id: int, url: str) -> bool:
```

and replace its body + companion `clear_discord_webhook` with:

```python
import sys as _sys
from dataclasses import dataclass


_REPO_BACKEND = str(_REPO_ROOT / "backend")
if _REPO_BACKEND not in _sys.path:
    _sys.path.insert(0, _REPO_BACKEND)

from core.discord import send_to_discord    # type: ignore[import-not-found]


@dataclass
class WebhookSetResult:
    persisted: bool
    test_ping_sent: bool


def _test_ping_payload(user_id: int) -> dict:
    return {
        "embeds": [{
            "title": "✅ Webhook 已設定",
            "description":
                f"來自 stock-dashboard admin CLI 的測試訊息。"
                f"user_id={user_id}",
            "color": 0x2ECC71,
        }]
    }


def set_discord_webhook(user_id: int, url: str) -> WebhookSetResult:
    """Validate format → persist → send test ping → rollback on failure.

    Raises ValueError if the URL fails the regex. Raises ValueError
    starting with "test ping" if the URL is well-formed but Discord
    rejects the test post.
    """
    if not _DISCORD_WEBHOOK_RE.match(url or ""):
        raise ValueError(
            "not a valid discord webhook URL "
            "(expected https://discord.com/api/webhooks/<id>/<token>)"
        )

    # Persist first so the test ping can read the URL back via
    # list_users_with_token. We undo on failure.
    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET discord_webhook_url = ? WHERE id = ?",
            (url, user_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return WebhookSetResult(persisted=False, test_ping_sent=False)

    try:
        send_to_discord(url, _test_ping_payload(user_id))
    except Exception as e:
        # Roll back persist.
        with connect() as conn:
            conn.execute(
                "UPDATE users SET discord_webhook_url = NULL WHERE id = ?",
                (user_id,),
            )
            conn.commit()
        raise ValueError(f"test ping failed: {e}") from e

    return WebhookSetResult(persisted=True, test_ping_sent=True)


def clear_discord_webhook(user_id: int) -> bool:
    """Set discord_webhook_url back to NULL. Returns True iff updated.

    Does NOT disable any notify_enabled strategies; use
    clear_discord_webhook_with_cascade for that flow.
    """
    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET discord_webhook_url = NULL WHERE id = ?",
            (user_id,),
        )
        conn.commit()
        return cur.rowcount > 0


def clear_discord_webhook_with_cascade(
    user_id: int, *, also_disable_strategies: bool,
) -> list[int]:
    """Clear the webhook AND optionally disable every notify_enabled
    strategy belonging to the user (so they don't keep firing without
    a destination).

    Returns the list of strategy ids that were enabled at the time of
    the call (so the CLI can render them to the operator), regardless
    of also_disable_strategies.
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT id FROM strategies "
            "WHERE user_id = ? AND notify_enabled = 1",
            (user_id,),
        ).fetchall()
        affected = [r["id"] for r in rows]

        conn.execute(
            "UPDATE users SET discord_webhook_url = NULL WHERE id = ?",
            (user_id,),
        )
        if also_disable_strategies and affected:
            conn.executemany(
                "UPDATE strategies SET notify_enabled = 0 WHERE id = ?",
                [(sid,) for sid in affected],
            )
        conn.commit()
    return affected
```

If the file structure makes the `from core.discord import send_to_discord` placement awkward, place the `_REPO_BACKEND` sys.path bump and `send_to_discord` import near the existing `from .db import connect` import — admin/db.py already does the same trick.

- [ ] **Step 8.4: Update the admin CLI**

In `admin/__main__.py`, find `_action_set_webhook`:

```python
def _action_set_webhook(user: dict) -> None:
    while True:
        url = questionary.text(...)
        ...
        try:
            ops.set_discord_webhook(user["id"], url)
        except ValueError as e:
            console.print(f"[red]Rejected:[/red] {e}")
            ...
```

Replace the `try` block with:

```python
        try:
            result = ops.set_discord_webhook(user["id"], url)
        except ValueError as e:
            console.print(f"[red]Rejected:[/red] {e}")
            if not questionary.confirm("Try again?", default=True).ask():
                return
            continue
        break
    if result.test_ping_sent:
        console.print(
            f"[green]Webhook set for '{user['name']}' "
            f"and test ping delivered.[/green]"
        )
    else:
        console.print(
            f"[yellow]Webhook saved for '{user['name']}' but the test "
            f"ping was skipped (user not found?).[/yellow]"
        )
    console.print(
        "[dim](Strategy notifications will now use this URL.)[/dim]"
    )
```

Then find the existing `clear_webhook` branch in `_user_action_menu`:

```python
        elif action == "clear_webhook":
            if questionary.confirm(...).ask():
                ops.clear_discord_webhook(user["id"])
                console.print("[green]Webhook cleared.[/green]")
```

Replace with:

```python
        elif action == "clear_webhook":
            affected = ops.clear_discord_webhook_with_cascade(
                user["id"], also_disable_strategies=False,
            )
            if affected:
                console.print(
                    f"[yellow]Warning: {len(affected)} active strategy "
                    f"row(s) will silently fail to send notifications "
                    f"until a new webhook is set.[/yellow]"
                )
                also = questionary.confirm(
                    "Auto-disable those strategies now?", default=False,
                ).ask()
                if also:
                    ops.clear_discord_webhook_with_cascade(
                        user["id"], also_disable_strategies=True,
                    )
                    console.print(
                        f"[green]Webhook cleared and "
                        f"{len(affected)} strategies disabled.[/green]"
                    )
                else:
                    console.print(
                        "[green]Webhook cleared "
                        "(strategies left enabled).[/green]"
                    )
            else:
                console.print("[green]Webhook cleared.[/green]")
```

NOTE: the call sequence in the affected-and-disable branch calls `clear_discord_webhook_with_cascade` twice. The first lists affected rows (and clears the URL). The second is a no-op for the URL (already null) and only sets `notify_enabled=0` because `also_disable_strategies=True`. This is intentional — the operator gets a chance to confirm before disabling.

A cleaner UX is to use a callable that *previews* without persisting — but that adds another function. Pragmatic pattern: two calls, second one disables.

- [ ] **Step 8.5: Run — should pass**

```bash
python3 -m pytest tests/test_admin_webhook_test_message.py -v 2>&1 | tail -20
```

Expected: 5 tests PASS.

- [ ] **Step 8.6: Run admin tests + full suite**

```bash
python3 -m pytest tests/test_admin_user_settings_ops.py tests/test_admin_webhook_test_message.py -q
python3 -m pytest tests/ -q
```

Expected: existing admin tests still pass; full suite is 451 PASS (446 + 5 new).

If the existing `test_admin_user_settings_ops.py` had assertions like `assert ops.set_discord_webhook(1, url)` returning a bool, they need updating to `result = ops.set_discord_webhook(1, url); assert result.persisted is True`. Inspect and patch any failures.

- [ ] **Step 8.7: Commit**

```bash
git add admin/ops.py admin/__main__.py tests/test_admin_webhook_test_message.py
# also tests/test_admin_user_settings_ops.py if it needed adjustments
git commit -m "$(cat <<'EOF'
feat(admin): webhook test-ping on set + cascade-disable on clear

set_discord_webhook now returns a WebhookSetResult and posts a small
"webhook configured" embed via core.discord.send_to_discord
immediately after persisting. If Discord rejects the test ping, the
persist is rolled back and the operator sees the failure.

clear_discord_webhook_with_cascade lists the user's currently-enabled
strategies and optionally disables them in the same flow; admin CLI's
"Clear Discord webhook URL" action surfaces the count and prompts.
EOF
)"
```

---

## Phase exit criteria

After all eight tasks are committed:

1. `python3 -m pytest tests/ -q` passes (≈ 451 tests).
2. `curl -H "Authorization: Bearer <token>" http://localhost:8000/api/strategies` returns the user's strategies (or `[]` if none exist + permission granted; 403 if permission off).
3. A real grant + create + enable + manual run-through of `evaluate_one` produces an embed in the user's Discord webhook (manual VPS smoke test post-deploy).
4. `git log --oneline master..HEAD` shows the eight phase commits.

P4 is then ready to merge. The next phase is **P5: frontend** — `/strategies` pages, condition builder, recharts equity curve, `useMe` gating.
