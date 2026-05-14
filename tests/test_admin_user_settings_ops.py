"""Tests for admin/ops.py user-listing + foreign-futures permission flip.

The conftest at tests/conftest.py already configures DB_PATH=:memory: and
runs init_db before each test; admin/db.py::connect() delegates that
sentinel to backend's cached in-memory connection so these tests see the
same `paul` row the migration seeded.
"""
from admin import ops


def test_list_users_with_token_includes_feature_flag():
    rows = ops.list_users_with_token()
    assert rows, "expected at least the seeded paul user"
    paul = next(u for u in rows if u["name"] == "paul")
    assert paul["can_view_foreign_futures"] is False


def test_set_foreign_futures_permission_round_trips():
    ops.set_foreign_futures_permission(1, True)
    paul = next(u for u in ops.list_users_with_token() if u["id"] == 1)
    assert paul["can_view_foreign_futures"] is True

    ops.set_foreign_futures_permission(1, False)
    paul = next(u for u in ops.list_users_with_token() if u["id"] == 1)
    assert paul["can_view_foreign_futures"] is False


def test_set_foreign_futures_permission_unknown_user_returns_false():
    assert ops.set_foreign_futures_permission(99999, True) is False
