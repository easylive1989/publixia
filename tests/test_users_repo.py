from repositories.users import (
    create_user, get_user_by_id, get_user_by_name, list_users,
    get_user_with_settings,
    set_foreign_futures_permission,
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
    """Newly seeded `paul` should have the foreign-futures gate off."""
    u = get_user_with_settings(1)
    assert u is not None
    assert u["name"] == "paul"
    assert u["can_view_foreign_futures"] is False


def test_set_foreign_futures_permission_toggles():
    set_foreign_futures_permission(1, True)
    assert get_user_with_settings(1)["can_view_foreign_futures"] is True
    set_foreign_futures_permission(1, False)
    assert get_user_with_settings(1)["can_view_foreign_futures"] is False


def test_set_foreign_futures_permission_unknown_user_returns_false():
    assert set_foreign_futures_permission(99999, True) is False
