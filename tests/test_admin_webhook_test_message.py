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
    assert "embeds" in args[1]


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
