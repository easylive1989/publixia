"""Repository tests for api_tokens table."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from datetime import datetime, timedelta, timezone

from repositories.api_tokens import (
    insert_token, find_active_by_hash, touch_last_used,
    list_tokens, revoke_token,
)
from repositories.users import create_user


def test_insert_and_find_token():
    token_id = insert_token("hash_abc", "sd_aaa", "label-a", user_id=1)
    assert isinstance(token_id, int)

    row = find_active_by_hash("hash_abc")
    assert row is not None
    assert row["id"] == token_id
    assert row["prefix"] == "sd_aaa"
    assert row["label"] == "label-a"
    assert row["user_id"] == 1
    assert row["revoked_at"] is None


def test_revoke_token_makes_it_inactive():
    token_id = insert_token("hash_revoked", "sd_rev", "to-revoke", user_id=1)
    assert revoke_token(token_id) is True

    row = find_active_by_hash("hash_revoked")
    assert row is None

    # Re-revoking returns False (already revoked)
    assert revoke_token(token_id) is False


def test_expired_token_not_returned_by_find_active():
    past = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).isoformat()
    insert_token("hash_expired", "sd_exp", "expired-token", user_id=1, expires_at=past)

    assert find_active_by_hash("hash_expired") is None


def test_touch_last_used_updates_timestamp():
    token_id = insert_token("hash_touch", "sd_tou", "touch-test", user_id=1)
    row_before = find_active_by_hash("hash_touch")
    assert row_before["last_used_at"] is None

    touch_last_used(token_id)

    row_after = find_active_by_hash("hash_touch")
    assert row_after["last_used_at"] is not None


def test_list_tokens_returns_all_including_revoked():
    insert_token("hash_l1", "sd_l1a", "list-1", user_id=1)
    rid = insert_token("hash_l2", "sd_l2a", "list-2", user_id=1)
    revoke_token(rid)

    rows = list_tokens()
    labels = {r["label"] for r in rows}
    assert "list-1" in labels
    assert "list-2" in labels


def test_inserting_second_active_token_for_user_revokes_prior():
    """Rotation: insert_token revokes any prior active row for the same user."""
    insert_token("hash_first", "sd_fst", "first", user_id=1)
    insert_token("hash_second", "sd_snd", "second", user_id=1)

    # First is now revoked, only second is active.
    assert find_active_by_hash("hash_first") is None
    assert find_active_by_hash("hash_second") is not None


def test_two_users_can_each_have_one_active_token():
    """The partial UNIQUE index is scoped to user_id."""
    create_user("alice")
    insert_token("hash_paul", "sd_pa", "paul-token", user_id=1)
    insert_token("hash_alice", "sd_al", "alice-token", user_id=2)

    assert find_active_by_hash("hash_paul") is not None
    assert find_active_by_hash("hash_alice") is not None
