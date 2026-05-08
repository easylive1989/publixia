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
        "can_view_top100":  False,
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


from api.dependencies import require_strategy_permission


def test_require_strategy_permission_403_when_off():
    """Default _fake_user has can_use_strategy=False; the dep rejects."""
    from fastapi import FastAPI, Depends
    app2 = FastAPI()

    @app2.get("/probe")
    def probe(user: dict = Depends(require_strategy_permission)):
        return {"ok": True}

    from api.dependencies import require_user
    app2.dependency_overrides[require_user] = lambda: {
        "id": 1, "name": "paul",
        "can_use_strategy": False, "can_view_top100": False,
        "discord_webhook_url": None,
    }
    from fastapi.testclient import TestClient
    r = TestClient(app2).get("/probe")
    assert r.status_code == 403
    assert r.json()["detail"] == "no strategy permission"


def test_require_strategy_permission_passes_when_on():
    from fastapi import FastAPI, Depends
    from db.connection import get_connection

    # Grant permission to paul in the DB so the dep's get_user_with_settings
    # call returns can_use_strategy=True.
    with get_connection() as conn:
        conn.execute("UPDATE users SET can_use_strategy=1 WHERE id=1")
        conn.commit()

    app2 = FastAPI()

    @app2.get("/probe")
    def probe(user: dict = Depends(require_strategy_permission)):
        return {"name": user["name"]}

    from api.dependencies import require_user
    app2.dependency_overrides[require_user] = lambda: {
        "id": 1, "name": "paul",
        "can_use_strategy": False, "can_view_top100": False,
        "discord_webhook_url": None,
    }
    from fastapi.testclient import TestClient
    r = TestClient(app2).get("/probe")
    assert r.status_code == 200
    assert r.json() == {"name": "paul"}
