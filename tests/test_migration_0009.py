"""Verify migration 0009 adds the can_view_top100 column to users."""
import db


def _columns(table: str) -> dict[str, dict]:
    rows = db.connection.get_connection().execute(
        f"PRAGMA table_info({table})"
    ).fetchall()
    return {r["name"]: dict(r) for r in rows}


def test_users_has_top100_permission_column():
    cols = _columns("users")
    assert "can_view_top100" in cols
    # Mirrors the can_use_strategy gating column: NOT NULL, DEFAULT 0.
    assert cols["can_view_top100"]["notnull"] == 1
    assert cols["can_view_top100"]["dflt_value"] == "0"


def test_seeded_user_defaults_to_no_top100_access():
    row = db.connection.get_connection().execute(
        "SELECT can_view_top100 FROM users WHERE name='paul'"
    ).fetchone()
    assert row is not None
    assert row["can_view_top100"] == 0
