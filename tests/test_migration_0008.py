"""Verify migration 0008 produces the expected FSE schema."""
import sqlite3

import pytest

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
    assert set(cols.keys()) == expected, (
        f"strategies columns mismatch: extra={set(cols.keys()) - expected}, "
        f"missing={expected - set(cols.keys())}"
    )
    assert "idx_strategies_user" in _indexes("strategies")
    assert "idx_strategies_notify_open" in _indexes("strategies")


def test_strategy_signals_table_shape():
    cols = _columns("strategy_signals")
    expected = {
        "id", "strategy_id", "kind", "signal_date", "close_at_signal",
        "fill_price", "exit_reason", "pnl_points", "pnl_amount", "message",
        "created_at",
    }
    assert set(cols.keys()) == expected, (
        f"strategy_signals columns mismatch: extra={set(cols.keys()) - expected}, "
        f"missing={expected - set(cols.keys())}"
    )
    assert "idx_signals_strategy_date" in _indexes("strategy_signals")


def test_strategies_check_constraints_enforced():
    """direction / contract / state / pending_exit_kind CHECK constraints must reject bad values."""
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
    with pytest.raises(sqlite3.IntegrityError):
        _insert(pending_exit_kind="GHOST")


def test_strategy_signals_kind_check_constraint_enforced():
    """kind CHECK must reject any value outside the six allowed kinds."""
    conn = db.connection.get_connection()
    conn.execute("INSERT INTO users (name) VALUES ('signal_kind_test_user')")
    user_id = conn.execute(
        "SELECT id FROM users WHERE name='signal_kind_test_user'"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO strategies "
        "(user_id, name, direction, contract, contract_size, "
        " entry_dsl, take_profit_dsl, stop_loss_dsl, "
        " state, created_at, updated_at) "
        "VALUES (?, 'sig-kind-test', 'long', 'TX', 1, "
        " '{}', '{}', '{}', 'idle', "
        " '2026-01-01T00:00:00', '2026-01-01T00:00:00')",
        (user_id,),
    )
    strategy_id = conn.execute(
        "SELECT id FROM strategies WHERE name='sig-kind-test'"
    ).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO strategy_signals "
            "(strategy_id, kind, signal_date, created_at) "
            "VALUES (?, 'ENTRY_FILL', '2026-01-02', '2026-01-02T00:00:00')",
            (strategy_id,),
        )

    # Same for a totally bogus kind
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO strategy_signals "
            "(strategy_id, kind, signal_date, created_at) "
            "VALUES (?, 'NOT_A_KIND', '2026-01-02', '2026-01-02T00:00:00')",
            (strategy_id,),
        )
