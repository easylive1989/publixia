"""Cross-layer seam test: admin/ops writes are visible to /api/me reads.

Both layers go through the same `db.connection.get_connection()` cached
connection in tests (admin/db.py delegates `:memory:` to backend), so a
permission grant or webhook set in admin/ops.py must be observable in the
very next /api/me call. This test locks that behavior in so that any
future drift (e.g., admin/ops opening its own connection) fails loudly.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from admin import ops
from main import app


client = TestClient(app)


def test_admin_grant_visible_to_me():
    ops.set_strategy_permission(1, True)
    body = client.get("/api/me").json()
    assert body["can_use_strategy"] is True


def test_admin_set_webhook_flips_has_webhook():
    body = client.get("/api/me").json()
    assert body["has_webhook"] is False

    with patch("admin.ops.send_to_discord"):
        ops.set_discord_webhook(
            1, "https://discord.com/api/webhooks/1/" + "x" * 60,
        )
    body = client.get("/api/me").json()
    assert body["has_webhook"] is True

    ops.clear_discord_webhook(1)
    body = client.get("/api/me").json()
    assert body["has_webhook"] is False
