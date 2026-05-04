from repositories.users import (
    create_user, get_user_by_id, get_user_by_name, list_users,
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
