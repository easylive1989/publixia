"""Token issuance + verification + auth-burst tracking."""
import hashlib
import logging
import secrets
import threading
from collections import deque
from datetime import datetime, timedelta, timezone

from core.discord import send_to_discord
from core.settings import settings
from repositories.api_tokens import (
    insert_token, find_active_by_hash, touch_last_used,
)

logger = logging.getLogger(__name__)


_TOKEN_PREFIX = "sd_"
_TOKEN_BODY_BYTES = 32
_DEFAULT_EXPIRY_DAYS = 365
_PREFIX_DISPLAY_LEN = 6

_BURST_WINDOW = timedelta(minutes=5)
_BURST_THRESHOLD = 5
_BURST_COOLDOWN = timedelta(hours=1)

_failures: dict[str, deque] = {}
_last_notified: dict[str, datetime] = {}
_burst_lock = threading.Lock()


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def issue_token(user_id: int, label: str,
                expiry_days: int | None = _DEFAULT_EXPIRY_DAYS) -> tuple[str, int]:
    """Issue a new token for `user_id`, revoking any prior active token.

    Returns (plaintext_token, db_id). Plaintext shown ONCE; only hash +
    display prefix stored. expiry_days=None for no-expiry tokens.
    """
    body = secrets.token_urlsafe(_TOKEN_BODY_BYTES)
    plaintext = f"{_TOKEN_PREFIX}{body}"
    digest = _hash_token(plaintext)
    display_prefix = f"{_TOKEN_PREFIX}{body[:_PREFIX_DISPLAY_LEN]}"

    expires_at = None
    if expiry_days is not None:
        expires_at = (datetime.now(timezone.utc).replace(tzinfo=None)
                      + timedelta(days=expiry_days)).isoformat()

    db_id = insert_token(digest, display_prefix, label, user_id, expires_at)
    logger.info(
        "token_issued id=%s user_id=%s label=%s prefix=%s",
        db_id, user_id, label, display_prefix,
    )
    return plaintext, db_id


def verify_token(plaintext: str | None) -> dict | None:
    """Return DB row if token is valid (active, not revoked, not expired). Else None."""
    if not plaintext:
        return None
    digest = _hash_token(plaintext)
    row = find_active_by_hash(digest)
    if row is None:
        return None
    touch_last_used(row["id"])
    return row


def track_auth_failure(client_ip: str) -> None:
    """Track 401 burst per client_ip; notify Discord ops on threshold breach."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    should_notify = False
    count = 0
    with _burst_lock:
        deq = _failures.setdefault(client_ip, deque())
        deq.append(now)
        while deq and (now - deq[0]) > _BURST_WINDOW:
            deq.popleft()
        count = len(deq)
        if count >= _BURST_THRESHOLD:
            last = _last_notified.get(client_ip)
            if not last or (now - last) >= _BURST_COOLDOWN:
                _last_notified[client_ip] = now
                should_notify = True

    if not should_notify:
        return

    webhook = settings.discord_ops_webhook_url
    if not webhook:
        logger.warning("auth_burst_no_ops_webhook ip=%s count=%d", client_ip, count)
        return
    payload = {
        "embeds": [{
            "title": "🚨 Stock Dashboard auth burst",
            "description": f"IP `{client_ip}` triggered {count} 401s in {_BURST_WINDOW}.",
            "color": 0xE74C3C,
        }]
    }
    try:
        send_to_discord(webhook.get_secret_value(), payload)
        logger.warning("auth_burst_notified ip=%s count=%d", client_ip, count)
    except Exception as e:
        logger.warning("auth_burst_notify_failed ip=%s error=%s", client_ip, e)
