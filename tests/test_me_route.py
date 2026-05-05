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
