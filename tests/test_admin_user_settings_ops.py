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
