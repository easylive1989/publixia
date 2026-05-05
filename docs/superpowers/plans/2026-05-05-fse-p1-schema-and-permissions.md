# FSE Phase 1 — Schema + Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the database schema for the Futures Strategy Engine (strategies + strategy_signals tables, users.can_use_strategy + users.discord_webhook_url columns) and the admin CLI controls to grant permission and configure each user's per-user Discord webhook. After P1, no strategy logic runs yet — but admins can configure who *would* be allowed once P3/P4 land, and `/api/me` reports the flags so the (future) frontend can gate its UI.

**Architecture:** One forward-only migration `0008_strategies.sql` that adds the two columns and creates both new tables + indexes (full schema, not staged across phases). New helper functions in `repositories/users.py` for the columns, no new repository module yet. New thin route module `api/routes/me.py` exposing `GET /api/me`. `admin/ops.py` gets three new helpers; `admin/__main__.py`'s list-users table gains two columns and the per-user submenu gains three actions (toggle strategy permission, set webhook, clear webhook). No backend strategy code lives in this phase.

**Tech Stack:** Python 3 / FastAPI / SQLite / pytest / questionary + rich (admin CLI).

**Spec reference:** `docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md` §3.1, §3.2, §3.3, §8.1 (`/api/me` + `require_strategy_permission` shape only — strategy endpoints land in P4), §8.3.

---

## File Structure

**Created:**
- `backend/db/migrations/0008_strategies.sql` — full FSE schema (users columns, strategies table, strategy_signals table, indexes).
- `backend/api/routes/me.py` — `GET /api/me` returning `{user_id, name, can_use_strategy, has_webhook}`.
- `backend/api/schemas/me.py` — `MeResponse` Pydantic model.
- `tests/test_migration_0008.py` — verifies the migration applies cleanly and the resulting schema matches expectations.
- `tests/test_me_route.py` — `/api/me` round-trip tests.
- `tests/test_admin_user_settings_ops.py` — covers the three new `admin/ops.py` helpers.

**Modified:**
- `backend/repositories/users.py` — add `set_strategy_permission`, `set_discord_webhook`, `clear_discord_webhook`; extend `get_user_by_id` (and a new `get_user_with_settings`) to surface the new columns.
- `backend/api/dependencies.py` — `require_user` keeps returning a user dict that now includes the two new columns.
- `backend/main.py` — register `me.router`.
- `admin/ops.py` — add `set_strategy_permission`, `set_discord_webhook`, `clear_discord_webhook`; extend `list_users_with_token` to also return `can_use_strategy` and a masked webhook display.
- `admin/__main__.py` — render two new columns in the users table; add three actions in `_user_action_menu`.
- `tests/test_users_repo.py` — add cases for the three new helpers and the new return shape.
- `ADMIN.md` — append a "Strategy permissions & per-user webhooks" section.
- `admin/README.md` — mention the new menu items in the workflow list.

**Out of scope for this phase (deferred to later phases):**
- Any code under `backend/services/strategy_*.py` (P2/P3).
- `api/routes/strategies.py` and `repositories/strategies.py` (P4 — even though the tables exist).
- The cascade "disabling strategies when clearing a webhook" warning (P4 — there are no enabled strategies to disable yet, so the helper is unnecessary in P1).
- Any frontend changes (P5).

---

## Task 1: Migration 0008 — full FSE schema

**Files:**
- Create: `backend/db/migrations/0008_strategies.sql`
- Create: `tests/test_migration_0008.py`

- [ ] **Step 1.1: Write the migration file**

Create `backend/db/migrations/0008_strategies.sql` with this exact content:

```sql
-- 0008_strategies.sql
--
-- Futures Strategy Engine — full schema in one shot.
-- See docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md
-- §3 for the design.
--
-- Adds two columns to users (permission flag + per-user Discord webhook),
-- and two new tables: strategies (with embedded hypothetical-position
-- state) and strategy_signals (entry/exit signal + fill log).

ALTER TABLE users ADD COLUMN can_use_strategy INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN discord_webhook_url TEXT;

CREATE TABLE strategies (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                     TEXT    NOT NULL,
    direction                TEXT    NOT NULL CHECK (direction IN ('long','short')),
    contract                 TEXT    NOT NULL CHECK (contract  IN ('TX','MTX','TMF')),
    contract_size            INTEGER NOT NULL DEFAULT 1,
    max_hold_days            INTEGER,
    entry_dsl                TEXT    NOT NULL,
    take_profit_dsl          TEXT    NOT NULL,
    stop_loss_dsl            TEXT    NOT NULL,
    notify_enabled           INTEGER NOT NULL DEFAULT 0,

    state                    TEXT    NOT NULL DEFAULT 'idle'
                              CHECK (state IN ('idle','pending_entry','open','pending_exit')),
    entry_signal_date        TEXT,
    entry_fill_date          TEXT,
    entry_fill_price         REAL,
    pending_exit_kind        TEXT,
    pending_exit_signal_date TEXT,

    last_error               TEXT,
    last_error_at            TEXT,

    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL,
    UNIQUE(user_id, name)
);

CREATE INDEX idx_strategies_user        ON strategies(user_id);
CREATE INDEX idx_strategies_notify_open ON strategies(notify_enabled, state)
                                            WHERE notify_enabled = 1;

CREATE TABLE strategy_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id     INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    kind            TEXT    NOT NULL CHECK (kind IN (
                      'ENTRY_SIGNAL', 'ENTRY_FILLED',
                      'EXIT_SIGNAL',  'EXIT_FILLED',
                      'MANUAL_RESET', 'RUNTIME_ERROR'
                    )),
    signal_date     TEXT    NOT NULL,
    close_at_signal REAL,
    fill_price      REAL,
    exit_reason     TEXT,
    pnl_points      REAL,
    pnl_amount      REAL,
    message         TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX idx_signals_strategy_date ON strategy_signals(strategy_id, signal_date DESC);
```

- [ ] **Step 1.2: Write the migration test (will fail until `init_db()` picks the file up)**

Create `tests/test_migration_0008.py`:

```python
"""Verify migration 0008 produces the expected FSE schema."""
import db


def _columns(table: str) -> dict[str, dict]:
    """Return {column_name: pragma_row_dict} for a table."""
    rows = db.connection.get_connection().execute(
        f"PRAGMA table_info({table})"
    ).fetchall()
    return {r["name"]: dict(r) for r in rows}


def _indexes(table: str) -> set[str]:
    rows = db.connection.get_connection().execute(
        f"PRAGMA index_list({table})"
    ).fetchall()
    return {r["name"] for r in rows}


def test_users_has_strategy_columns():
    cols = _columns("users")
    assert "can_use_strategy" in cols
    assert cols["can_use_strategy"]["notnull"] == 1
    assert cols["can_use_strategy"]["dflt_value"] == "0"
    assert "discord_webhook_url" in cols
    assert cols["discord_webhook_url"]["notnull"] == 0


def test_strategies_table_shape():
    cols = _columns("strategies")
    expected = {
        "id", "user_id", "name", "direction", "contract", "contract_size",
        "max_hold_days", "entry_dsl", "take_profit_dsl", "stop_loss_dsl",
        "notify_enabled", "state", "entry_signal_date", "entry_fill_date",
        "entry_fill_price", "pending_exit_kind", "pending_exit_signal_date",
        "last_error", "last_error_at", "created_at", "updated_at",
    }
    assert expected.issubset(cols.keys())
    assert "idx_strategies_user" in _indexes("strategies")
    assert "idx_strategies_notify_open" in _indexes("strategies")


def test_strategy_signals_table_shape():
    cols = _columns("strategy_signals")
    expected = {
        "id", "strategy_id", "kind", "signal_date", "close_at_signal",
        "fill_price", "exit_reason", "pnl_points", "pnl_amount", "message",
        "created_at",
    }
    assert expected.issubset(cols.keys())
    assert "idx_signals_strategy_date" in _indexes("strategy_signals")


def test_strategies_check_constraints_enforced():
    """direction / contract / state CHECK constraints must reject bad values."""
    import pytest
    import sqlite3
    conn = db.connection.get_connection()
    conn.execute("INSERT INTO users (name) VALUES ('migration_test_user')")
    user_id = conn.execute(
        "SELECT id FROM users WHERE name='migration_test_user'"
    ).fetchone()[0]

    base = {
        "user_id": user_id, "name": "s",
        "direction": "long", "contract": "TX",
        "contract_size": 1, "max_hold_days": None,
        "entry_dsl": "{}", "take_profit_dsl": "{}", "stop_loss_dsl": "{}",
        "notify_enabled": 0, "state": "idle",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }

    def _insert(**override):
        params = {**base, **override}
        cols = ", ".join(params.keys())
        placeholders = ", ".join("?" for _ in params)
        conn.execute(
            f"INSERT INTO strategies ({cols}) VALUES ({placeholders})",
            tuple(params.values()),
        )

    with pytest.raises(sqlite3.IntegrityError):
        _insert(direction="sideways")
    with pytest.raises(sqlite3.IntegrityError):
        _insert(contract="ES")
    with pytest.raises(sqlite3.IntegrityError):
        _insert(state="halfway")
```

- [ ] **Step 1.3: Run the migration test — should now PASS because `init_db()` (called from conftest) picks up new `.sql` files automatically**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/test_migration_0008.py -v`
Expected: 4 tests PASS.

If a test fails, the most likely causes are: typo in the SQL file, or a column name that doesn't match the spec. Read the failing assertion, fix the SQL, rerun.

- [ ] **Step 1.4: Verify the rest of the test suite still passes**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/ -x -q`
Expected: every test PASSES (no regressions; the new columns default to safe values, so existing tests on `users` should be unaffected).

- [ ] **Step 1.5: Commit**

```bash
cd /Users/paulwu/Documents/Github/publixia
git add backend/db/migrations/0008_strategies.sql tests/test_migration_0008.py
git commit -m "$(cat <<'EOF'
feat(strategy): migration 0008 - users flags + strategies/signals tables

Add the full Futures Strategy Engine schema in one shot: two new columns
on users (can_use_strategy, discord_webhook_url) plus the strategies and
strategy_signals tables with their indexes. No application code reads
from the new tables yet — this phase only lays the schema groundwork so
admin permission/webhook controls can land next.
EOF
)"
```

---

## Task 2: `repositories/users.py` — settings helpers

**Files:**
- Modify: `backend/repositories/users.py`
- Modify: `tests/test_users_repo.py`

- [ ] **Step 2.1: Add failing tests for the new helpers**

Append to `tests/test_users_repo.py`:

```python
from repositories.users import (
    get_user_with_settings,
    set_strategy_permission,
    set_discord_webhook,
    clear_discord_webhook,
)


def test_get_user_with_settings_defaults():
    """Newly seeded `paul` should have can_use_strategy=False and no webhook."""
    u = get_user_with_settings(1)
    assert u is not None
    assert u["name"] == "paul"
    assert u["can_use_strategy"] is False
    assert u["discord_webhook_url"] is None


def test_set_strategy_permission_toggles():
    set_strategy_permission(1, True)
    assert get_user_with_settings(1)["can_use_strategy"] is True
    set_strategy_permission(1, False)
    assert get_user_with_settings(1)["can_use_strategy"] is False


def test_set_strategy_permission_unknown_user_returns_false():
    assert set_strategy_permission(99999, True) is False


def test_set_and_clear_discord_webhook():
    url = "https://discord.com/api/webhooks/123/abc"
    set_discord_webhook(1, url)
    assert get_user_with_settings(1)["discord_webhook_url"] == url

    clear_discord_webhook(1)
    assert get_user_with_settings(1)["discord_webhook_url"] is None


def test_set_discord_webhook_unknown_user_returns_false():
    assert set_discord_webhook(99999, "https://x") is False
```

- [ ] **Step 2.2: Run tests — they should FAIL with ImportError**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/test_users_repo.py -v`
Expected: ImportError on `get_user_with_settings`, `set_strategy_permission`, `set_discord_webhook`, `clear_discord_webhook`.

- [ ] **Step 2.3: Implement the new helpers**

Append to `backend/repositories/users.py`:

```python
def get_user_with_settings(user_id: int) -> Optional[dict]:
    """Like get_user_by_id but also returns FSE-related columns.

    Booleans are decoded from SQLite's INTEGER 0/1 to Python bool so callers
    don't have to remember the underlying storage.
    """
    row = get_connection().execute(
        "SELECT id, name, created_at, "
        "       can_use_strategy, discord_webhook_url "
        "FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["can_use_strategy"] = bool(d["can_use_strategy"])
    return d


def set_strategy_permission(user_id: int, granted: bool) -> bool:
    """Toggle can_use_strategy. Returns True iff a row was updated."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET can_use_strategy = ? WHERE id = ?",
        (1 if granted else 0, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def set_discord_webhook(user_id: int, url: str) -> bool:
    """Store a per-user webhook (plaintext). Returns True iff updated."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET discord_webhook_url = ? WHERE id = ?",
        (url, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def clear_discord_webhook(user_id: int) -> bool:
    """Set discord_webhook_url back to NULL. Returns True iff updated."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET discord_webhook_url = NULL WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    return cur.rowcount > 0
```

- [ ] **Step 2.4: Run tests — should PASS**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/test_users_repo.py -v`
Expected: all tests in this file PASS (existing 3 + new 5 = 8).

- [ ] **Step 2.5: Commit**

```bash
git add backend/repositories/users.py tests/test_users_repo.py
git commit -m "$(cat <<'EOF'
feat(strategy): users repo helpers for permission + webhook

Add get_user_with_settings + set_strategy_permission + set_discord_webhook
+ clear_discord_webhook. These back the admin CLI controls and the
/api/me route landing in subsequent commits.
EOF
)"
```

---

## Task 3: `GET /api/me` route

**Files:**
- Create: `backend/api/schemas/me.py`
- Create: `backend/api/routes/me.py`
- Create: `tests/test_me_route.py`
- Modify: `backend/main.py`

- [ ] **Step 3.1: Add the response schema**

Create `backend/api/schemas/me.py`:

```python
"""Response schema for GET /api/me."""
from pydantic import BaseModel


class MeResponse(BaseModel):
    user_id:          int
    name:             str
    can_use_strategy: bool
    has_webhook:      bool
```

- [ ] **Step 3.2: Write the failing route test**

Create `tests/test_me_route.py`:

```python
"""GET /api/me — round-trip tests against the in-memory DB.

The conftest overrides require_user to always resolve to paul (id=1), so
these tests exercise the route using whatever state we set on row id=1.
"""
from fastapi.testclient import TestClient

from main import app
from repositories.users import set_strategy_permission, set_discord_webhook


client = TestClient(app)


def test_me_defaults_for_seeded_user():
    r = client.get("/api/me")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "user_id":          1,
        "name":             "paul",
        "can_use_strategy": False,
        "has_webhook":      False,
    }


def test_me_reflects_strategy_permission_grant():
    set_strategy_permission(1, True)
    body = client.get("/api/me").json()
    assert body["can_use_strategy"] is True


def test_me_reflects_webhook_set():
    set_discord_webhook(1, "https://discord.com/api/webhooks/x/y")
    body = client.get("/api/me").json()
    assert body["has_webhook"] is True
    # The route MUST NOT leak the URL itself.
    assert "discord_webhook_url" not in body
    assert "discord.com" not in str(body)
```

- [ ] **Step 3.3: Run the test — should FAIL with 404 (route not registered)**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/test_me_route.py -v`
Expected: FAIL — 404 on every request because `/api/me` doesn't exist yet.

- [ ] **Step 3.4: Implement the route**

Create `backend/api/routes/me.py`:

```python
"""GET /api/me — current user's identity + FSE feature flags.

This route is the single source of truth the frontend polls on app boot
to decide whether to render the strategy section and whether the
"enable notifications" toggle should be active.
"""
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_user
from api.schemas.me import MeResponse
from repositories.users import get_user_with_settings

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeResponse)
def get_me(user: dict = Depends(require_user)) -> MeResponse:
    settings = get_user_with_settings(user["id"])
    if settings is None:                       # defensive — should not happen
        raise HTTPException(status_code=401, detail="Token user not found")
    return MeResponse(
        user_id          = settings["id"],
        name             = settings["name"],
        can_use_strategy = settings["can_use_strategy"],
        has_webhook      = settings["discord_webhook_url"] is not None,
    )
```

- [ ] **Step 3.5: Register the router**

In `backend/main.py`, edit the imports and `app.include_router` block.

Replace this line:

```python
from api.routes import indicators, stocks, fundamentals, news, futures
```

with:

```python
from api.routes import indicators, stocks, fundamentals, news, futures, me
```

Then add this line after `app.include_router(futures.router)`:

```python
app.include_router(me.router)
```

- [ ] **Step 3.6: Run the test — should PASS**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/test_me_route.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 3.7: Run the full backend suite to check for regressions**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/ -x -q`
Expected: every test PASSES.

- [ ] **Step 3.8: Commit**

```bash
git add backend/api/schemas/me.py backend/api/routes/me.py backend/main.py tests/test_me_route.py
git commit -m "$(cat <<'EOF'
feat(api): GET /api/me with FSE feature flags

Expose can_use_strategy and has_webhook so the frontend can gate the
strategy section without leaking the webhook URL itself. Backed by the
new users.* helpers; auth still goes through the existing require_user
dependency.
EOF
)"
```

---

## Task 4: `admin/db.py` + `admin/ops.py` — settings helpers + extended user listing

**Files:**
- Modify: `admin/db.py`
- Modify: `admin/ops.py`
- Create: `tests/test_admin_user_settings_ops.py`

- [ ] **Step 4.1: Make `admin/db.py::connect()` test-friendly**

The conftest puts the test DB at `:memory:`, but `admin/db.py::connect()` currently rejects non-existent paths with `FileNotFoundError`. Add a small accommodation so `:memory:` delegates to backend's cached in-memory connection — the only way for admin code and backend code to see the same data inside a test.

Replace the body of `admin/db.py::connect()` with:

```python
def connect() -> sqlite3.Connection:
    path = db_path()
    if str(path) == ":memory:":
        # Test path: share backend's cached :memory: connection so admin
        # code and backend code see the same database within a pytest run.
        import sys
        backend_dir = str(_REPO_ROOT / "backend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from db.connection import get_connection as _backend_conn  # type: ignore
        return _backend_conn()
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found at {path}. Set DB_PATH or copy the SQLite "
            f"file to {_DEFAULT_DB}."
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
```

This is a no-op for production (`DB_PATH` is a real file there) and unlocks ergonomic tests.

- [ ] **Step 4.2: Write the failing tests**

Create `tests/test_admin_user_settings_ops.py`:

```python
"""Tests for admin/ops.py FSE additions: permission, webhook, masked listing.

The conftest at tests/conftest.py already configures DB_PATH=:memory: and
runs init_db before each test; admin/db.py::connect() now delegates that
sentinel to backend's cached in-memory connection so these tests see the
same `paul` row the migration seeded.
"""
import pytest

from admin import ops


def test_list_users_with_token_includes_strategy_and_webhook_fields():
    """The admin listing now returns the two new FSE columns."""
    rows = ops.list_users_with_token()
    assert rows, "expected at least the seeded paul user"
    paul = next(u for u in rows if u["name"] == "paul")
    assert paul["can_use_strategy"] is False
    assert paul["webhook_display"] == "—"          # masked render of NULL


def test_set_strategy_permission_round_trips():
    ops.set_strategy_permission(1, True)
    rows = ops.list_users_with_token()
    paul = next(u for u in rows if u["id"] == 1)
    assert paul["can_use_strategy"] is True

    ops.set_strategy_permission(1, False)
    rows = ops.list_users_with_token()
    paul = next(u for u in rows if u["id"] == 1)
    assert paul["can_use_strategy"] is False


def test_set_discord_webhook_validates_format():
    with pytest.raises(ValueError, match="discord webhook"):
        ops.set_discord_webhook(1, "https://example.com/not-discord")
    with pytest.raises(ValueError, match="discord webhook"):
        ops.set_discord_webhook(1, "")


def test_set_discord_webhook_stores_and_masks():
    url = "https://discord.com/api/webhooks/123456789/abcdefghijklmnopqrstuvwxyz"
    ops.set_discord_webhook(1, url)
    rows = ops.list_users_with_token()
    paul = next(u for u in rows if u["id"] == 1)
    # The display masks the middle segments but keeps host + tail visible
    # so the admin can still distinguish "set vs not set" and spot a typo.
    assert paul["webhook_display"].startswith("https://discord.com/")
    assert "..." in paul["webhook_display"]
    assert paul["webhook_display"].endswith(url[-4:])


def test_clear_discord_webhook_returns_to_dash():
    ops.set_discord_webhook(
        1, "https://discord.com/api/webhooks/1/" + "x" * 60,
    )
    ops.clear_discord_webhook(1)
    rows = ops.list_users_with_token()
    paul = next(u for u in rows if u["id"] == 1)
    assert paul["webhook_display"] == "—"


def test_set_discord_webhook_accepts_discordapp_alias():
    """Discord still serves webhooks under the discordapp.com host."""
    ops.set_discord_webhook(
        1, "https://discordapp.com/api/webhooks/1/" + "x" * 60,
    )
    rows = ops.list_users_with_token()
    paul = next(u for u in rows if u["id"] == 1)
    assert "discordapp.com" in paul["webhook_display"]
```

- [ ] **Step 4.3: Run the tests — they should FAIL with AttributeError + KeyError**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/test_admin_user_settings_ops.py -v`
Expected: most tests fail because `ops.set_strategy_permission` etc. don't exist; `list_users_with_token` doesn't return `can_use_strategy` / `webhook_display`.

- [ ] **Step 4.4: Extend `admin/ops.py`**

Add this regex constant near the top of `admin/ops.py` (under the existing constants block):

```python
import re

_DISCORD_WEBHOOK_RE = re.compile(
    r"^https://(?:discord|discordapp)\.com/api/webhooks/\d+/[\w-]+$"
)


def _mask_webhook(url: str | None) -> str:
    """Render a webhook URL with the secret middle elided. NULL -> '—'."""
    if not url:
        return "—"
    # Format: https://discord.com/api/webhooks/<id>/<token>
    # We keep the host + the path prefix and the final 4 chars of the token.
    head, _, tail = url.rpartition("/")
    if not tail or len(tail) < 8:
        return f"{head}/...{tail[-4:] if tail else ''}"
    return f"{head}/...{tail[-4:]}"
```

Replace the body of `list_users_with_token` so its SQL also pulls the FSE columns and the returned dict carries `can_use_strategy` (bool) and `webhook_display` (masked string):

```python
def list_users_with_token() -> list[dict]:
    """Return users joined with their active-token status + FSE settings.

    status ∈ {"active", "expired", "none"}.
    Each row also carries:
      - can_use_strategy: bool
      - webhook_display:  str   (masked URL or "—")
    """
    now = _now_iso()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.name, u.created_at,
                   u.can_use_strategy,
                   u.discord_webhook_url,
                   t.id          AS token_id,
                   t.prefix      AS token_prefix,
                   t.expires_at  AS token_expires_at,
                   t.last_used_at
            FROM users u
            LEFT JOIN api_tokens t
              ON t.user_id = u.id AND t.revoked_at IS NULL
            ORDER BY u.id
            """
        ).fetchall()

    out: list[dict] = []
    for r in rows:
        d = dict(r)
        if d["token_id"] is None:
            d["token_status"] = "none"
        elif d["token_expires_at"] and d["token_expires_at"] < now:
            d["token_status"] = "expired"
        else:
            d["token_status"] = "active"
        d["can_use_strategy"] = bool(d["can_use_strategy"])
        d["webhook_display"] = _mask_webhook(d["discord_webhook_url"])
        out.append(d)
    return out
```

Append the three new helpers to the bottom of the file:

```python
def set_strategy_permission(user_id: int, granted: bool) -> bool:
    """Toggle can_use_strategy. Returns True iff a row was updated."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET can_use_strategy = ? WHERE id = ?",
            (1 if granted else 0, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def set_discord_webhook(user_id: int, url: str) -> bool:
    """Validate format + persist a per-user Discord webhook.

    Raises ValueError if the URL does not look like a Discord webhook.
    Returns True iff the user row was updated.
    """
    if not _DISCORD_WEBHOOK_RE.match(url or ""):
        raise ValueError(
            "not a valid discord webhook URL "
            "(expected https://discord.com/api/webhooks/<id>/<token>)"
        )
    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET discord_webhook_url = ? WHERE id = ?",
            (url, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def clear_discord_webhook(user_id: int) -> bool:
    """Set discord_webhook_url back to NULL. Returns True iff updated."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET discord_webhook_url = NULL WHERE id = ?",
            (user_id,),
        )
        conn.commit()
        return cur.rowcount > 0
```

- [ ] **Step 4.5: Run the tests — should PASS**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/test_admin_user_settings_ops.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 4.6: Run the full suite**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/ -x -q`
Expected: all PASS.

- [ ] **Step 4.7: Commit**

```bash
git add admin/db.py admin/ops.py tests/test_admin_user_settings_ops.py
git commit -m "$(cat <<'EOF'
feat(admin): permission + webhook helpers; extend list_users_with_token

list_users_with_token now also surfaces can_use_strategy (bool) and a
masked webhook display ("—" or https://.../...<last4>"). New helpers:
set_strategy_permission, set_discord_webhook (validates format), and
clear_discord_webhook. The webhook regex matches both discord.com and
discordapp.com hosts since Discord still serves both.

admin/db.py::connect() also gains a :memory: branch that shares the
backend's cached in-memory connection, so admin ops can be exercised
in pytest against the same DB the conftest initialises.
EOF
)"
```

---

## Task 5: `admin/__main__.py` — table columns + per-user submenu

**Files:**
- Modify: `admin/__main__.py`

This task is interactive UI; we verify it manually. The underlying `ops.*` calls were unit-tested in Task 4.

- [ ] **Step 5.1: Extend the rendered users table**

In `admin/__main__.py`, replace the body of `_render_users_table` with this version (two new columns `STRATEGY` and `WEBHOOK`):

```python
def _render_users_table(users: list[dict]) -> None:
    if not users:
        console.print("[dim](no users)[/dim]")
        return
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", justify="right")
    table.add_column("NAME")
    table.add_column("CREATED")
    table.add_column("TOKEN PREFIX")
    table.add_column("TOKEN EXPIRES")
    table.add_column("STATUS")
    table.add_column("STRATEGY")
    table.add_column("WEBHOOK")

    status_color = {
        "active": "[green]active[/green]",
        "expired": "[yellow]expired[/yellow]",
        "none": "[dim]none[/dim]",
    }
    for u in users:
        strategy_cell = (
            "[green]✓[/green]" if u.get("can_use_strategy")
            else "[dim]✗[/dim]"
        )
        webhook_cell = u.get("webhook_display", "—")
        if webhook_cell == "—":
            webhook_cell = "[dim]—[/dim]"
        table.add_row(
            str(u["id"]),
            u["name"],
            u["created_at"] or "-",
            u["token_prefix"] or "-",
            (u["token_expires_at"] or "never") if u["token_id"] else "-",
            status_color.get(u["token_status"], u["token_status"]),
            strategy_cell,
            webhook_cell,
        )
    console.print(table)
```

- [ ] **Step 5.2: Extend `_user_action_menu` with three new actions**

Replace the body of `_user_action_menu` with this version:

```python
def _user_action_menu(user: dict) -> None:
    while True:
        action = questionary.select(
            f"User '{user['name']}' (id={user['id']}, "
            f"token={user['token_status']}, "
            f"strategy={'on' if user.get('can_use_strategy') else 'off'}):",
            choices=[
                questionary.Choice("Refresh token", value="refresh"),
                questionary.Choice(
                    "Revoke active token",
                    value="revoke",
                    disabled=None if user["token_status"] == "active" else "no active token",
                ),
                questionary.Choice("Toggle strategy permission", value="toggle_strategy"),
                questionary.Choice("Set Discord webhook URL", value="set_webhook"),
                questionary.Choice(
                    "Clear Discord webhook URL",
                    value="clear_webhook",
                    disabled=None if user.get("discord_webhook_url") else "no webhook set",
                ),
                questionary.Choice("[back]", value="back"),
            ],
        ).ask()

        if action in (None, "back"):
            return
        if action == "refresh":
            _action_refresh_token(user)
        elif action == "revoke":
            if questionary.confirm(
                f"Revoke active token for '{user['name']}'?", default=False,
            ).ask():
                if ops.revoke_active_token(user["id"]):
                    console.print("[green]Token revoked.[/green]")
                else:
                    console.print("[yellow]No active token to revoke.[/yellow]")
        elif action == "toggle_strategy":
            new_state = not bool(user.get("can_use_strategy"))
            ops.set_strategy_permission(user["id"], new_state)
            console.print(
                f"[green]Strategy permission for '{user['name']}' = "
                f"{'ON' if new_state else 'OFF'}[/green]"
            )
        elif action == "set_webhook":
            _action_set_webhook(user)
        elif action == "clear_webhook":
            if questionary.confirm(
                f"Clear webhook for '{user['name']}'? "
                "(Strategies that depend on it will fail to send "
                "notifications until a new URL is set.)",
                default=False,
            ).ask():
                ops.clear_discord_webhook(user["id"])
                console.print("[green]Webhook cleared.[/green]")

        # Refresh the row so subsequent menu iterations see new state.
        users = ops.list_users_with_token()
        latest = next((u for u in users if u["id"] == user["id"]), None)
        if latest is None:
            return
        user = latest
```

- [ ] **Step 5.3: Add the `_action_set_webhook` helper**

Insert this function below `_action_refresh_token` (anywhere in the module is fine — keep it grouped with the other `_action_*` helpers):

```python
def _action_set_webhook(user: dict) -> None:
    url = questionary.text(
        "Discord webhook URL:",
        validate=lambda v: True if v.strip().startswith("https://") else (
            "URL must start with https://"
        ),
    ).ask()
    if not url:
        return
    url = url.strip()
    try:
        ops.set_discord_webhook(user["id"], url)
    except ValueError as e:
        console.print(f"[red]Rejected:[/red] {e}")
        return
    console.print(
        f"[green]Webhook set for '{user['name']}'.[/green] "
        f"[dim](Strategy notifications will use this URL.)[/dim]"
    )
```

- [ ] **Step 5.4: Manual verification — list view**

In one terminal, create a throwaway DB file with migrations applied:

```bash
cd /Users/paulwu/Documents/Github/publixia
export DB_PATH=/tmp/fse_p1_manual.db
rm -f "$DB_PATH"
python3 -c "import sys; sys.path.insert(0, 'backend'); import db; db.init_db()"
```

Then run the admin CLI against that DB (the env var carries over, since pydantic settings reads `DB_PATH` case-insensitively):

```bash
admin/.venv/bin/python -m admin
```

If `admin/.venv` does not exist yet, follow `admin/README.md` to create it (`cd admin && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..`).

Expected:
- Top menu shows `List users`. Picking it renders an 8-column table; for `paul` you should see `STRATEGY = ✗` and `WEBHOOK = —`.

- [ ] **Step 5.5: Manual verification — toggle + set + clear**

In the same `python -m admin` session:

1. Pick `List users` → pick `paul`.
2. Choose `Toggle strategy permission`. Confirm console prints `Strategy permission for 'paul' = ON`. The row is re-rendered (next iteration of the menu) but you'll only see it if you `[back]` to the list — that's fine; just go back and pick `paul` again, the strategy column should now show ✓.
3. Choose `Set Discord webhook URL`. Paste a fake URL `https://example.com/x` — expect the rejection message. Then paste `https://discord.com/api/webhooks/1/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` — expect the success line.
4. Go back to the user list — `WEBHOOK` column shows the masked URL ending in `aaaa` and `STRATEGY` shows ✓.
5. Re-enter `paul`, choose `Clear Discord webhook URL`, confirm — webhook column returns to `—`.

- [ ] **Step 5.6: Run the full test suite (catch any incidental breakage)**

Run: `cd /Users/paulwu/Documents/Github/publixia && python3 -m pytest tests/ -x -q`
Expected: all PASS.

- [ ] **Step 5.7: Commit**

```bash
git add admin/__main__.py
git commit -m "$(cat <<'EOF'
feat(admin): per-user strategy permission + webhook actions in CLI

The list-users table grows two columns (STRATEGY, WEBHOOK) and the
per-user submenu gains three actions: toggle strategy permission, set
discord webhook, clear webhook. Webhook input goes through ops.* which
validates format and stores plaintext (matching the existing .env-style
secret model). The list re-fetches after each action so the next menu
iteration reflects the change.
EOF
)"
```

---

## Task 6: Documentation

**Files:**
- Modify: `ADMIN.md`
- Modify: `admin/README.md`

- [ ] **Step 6.1: Append a new section to `ADMIN.md`**

Insert this section in `ADMIN.md` between the existing `## User & token management` section and `## Auto-tracked Taiwan top-100`. Locate the closing of `## User & token management` (the line right before `## Auto-tracked Taiwan top-100`) and add the new section:

```markdown
## Strategy permissions & per-user Discord webhooks

The Futures Strategy Engine (`docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md`) is gated by two new per-user fields on the `users` table:

- `can_use_strategy` — boolean. When `0`, the user gets `403` from any
  `/api/strategies/*` endpoint (introduced in P4) and the frontend hides
  the strategy section. Default `0` for every user including `paul`.
- `discord_webhook_url` — nullable text. Per-user webhook for strategy
  notifications. Stored plaintext (same model as the project's `.env`).
  Without one set, the user cannot enable real-time notifications on a
  strategy.

Both are managed exclusively through the admin CLI's per-user submenu.

### Workflows

- **Grant strategy access**: `List users → pick user → Toggle strategy
  permission`. Toggling is idempotent — choosing the action a second
  time revokes.
- **Set per-user webhook**: `List users → pick user → Set Discord
  webhook URL`. The CLI validates the URL pattern
  `https://(discord|discordapp).com/api/webhooks/<id>/<token>` and
  rejects anything else.
- **Rotate webhook**: just call `Set Discord webhook URL` again — it
  overwrites the previous URL.
- **Clear webhook**: `Clear Discord webhook URL`. Asks for confirmation
  because strategies that depend on it will then silently fail to send
  notifications. (In a later phase we will additionally offer to
  auto-disable the user's notify-enabled strategies in the same flow.)

### Audit

The list view shows two new columns, `STRATEGY` (✓/✗) and `WEBHOOK`
(masked URL or `—`). The webhook display elides the secret token
segment so the table can be safely shared/screenshotted.

For a deeper inspection (or to dump every user's raw URL), query the DB
directly:

```bash
sqlite3 /opt/stock-dashboard/backend/stock_dashboard.db \
  "SELECT id, name, can_use_strategy, discord_webhook_url FROM users"
```
```

- [ ] **Step 6.2: Update `admin/README.md`**

In `admin/README.md`'s `## Features` section, append three new bullets after the existing `Restart backend service` bullet:

```markdown
- **Toggle strategy permission** — flips `users.can_use_strategy` for the
  selected user. Hidden gate for the Futures Strategy Engine; off by
  default.
- **Set Discord webhook URL** — stores a per-user webhook for strategy
  notifications. Validates `https://(discord|discordapp).com/api/webhooks/<id>/<token>`
  before persisting.
- **Clear Discord webhook URL** — sets the column back to NULL. Strategies
  that need it to send notifications will then silently skip until a new
  URL is configured.
```

- [ ] **Step 6.3: Commit**

```bash
git add ADMIN.md admin/README.md
git commit -m "$(cat <<'EOF'
docs: admin runbook entries for strategy permission + webhook

Document the two new per-user fields, the three new admin CLI actions,
the masked-display semantics, and how to inspect the raw DB rows. The
strategy section in ADMIN.md links back to the FSE design spec for
context.
EOF
)"
```

---

## Phase exit criteria

After all six tasks are committed:

1. `python3 -m pytest tests/ -q` passes (no regressions; six new test functions land in P1).
2. `python3 -m admin` (against a populated DB) shows the new table columns and the three new actions per user.
3. `curl -H "Authorization: Bearer <token>" http://localhost:8000/api/me` returns
   `{"user_id": 1, "name": "paul", "can_use_strategy": false, "has_webhook": false}` for a fresh DB.
4. `git log --oneline -7` shows the six P1 commits in order.

P1 is then ready to merge to master and deploy. Migration 0008 will run automatically on the VPS via `init_db()`; no manual steps required.

The next phase is **P2: DSL + Backtrader translation**, which will add `services/strategy_dsl.py`, `services/strategy_backtest.py`, and the conformance test suite, but no API or frontend yet.
