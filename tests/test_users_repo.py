from repositories.users import (
    create_user, get_user_by_id, get_user_by_name, list_users,
    get_user_with_settings,
    set_strategy_permission,
    set_discord_webhook,
    clear_discord_webhook,
)


def test_default_paul_seeded():
    assert get_user_by_name('paul') is not None


def test_create_and_lookup():
    uid = create_user('alice')
    assert uid > 1
    assert get_user_by_id(uid)['name'] == 'alice'


def test_list_users_includes_seed_and_new():
    create_user('bob')
    names = [u['name'] for u in list_users()]
    assert 'paul' in names
    assert 'bob' in names


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


def test_clear_discord_webhook_unknown_user_returns_false():
    assert clear_discord_webhook(99999) is False
