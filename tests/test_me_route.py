"""GET /api/me — round-trip tests against the in-memory DB.

The conftest overrides require_user to always resolve to paul (id=1), so
these tests exercise the route using whatever state we set on row id=1.
"""
from fastapi.testclient import TestClient

from main import app
from repositories.users import set_foreign_futures_permission


client = TestClient(app)


def test_me_defaults_for_seeded_user():
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json() == {
        "user_id":                  1,
        "name":                     "paul",
        "can_view_foreign_futures": False,
    }


def test_me_reflects_foreign_futures_permission_grant():
    set_foreign_futures_permission(1, True)
    body = client.get("/api/me").json()
    assert body["can_view_foreign_futures"] is True
