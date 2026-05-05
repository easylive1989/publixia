"""Data operations for the admin CLI.

Independent from the backend code — talks to SQLite directly. Token
issuance mirrors backend/services/token_service.py: sd_-prefixed,
sha256-hashed, one active token per user (revoke prior on insert).
"""
import hashlib
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from .db import connect


_TOKEN_PREFIX = "sd_"
_TOKEN_BODY_BYTES = 32
_PREFIX_DISPLAY_LEN = 6
_DEFAULT_EXPIRY_DAYS = 365

_DISCORD_WEBHOOK_RE = re.compile(
    r"^https://(?:discord|discordapp)\.com/api/webhooks/\d+/[\w-]+$"
)


def _mask_webhook(url: str | None) -> str:
    """Render a webhook URL with the secret middle elided. NULL -> '—'."""
    if not url:
        return "—"
    head, _, tail = url.rpartition("/")
    if not tail or len(tail) < 8:
        return f"{head}/...{tail[-4:] if tail else ''}"
    return f"{head}/...{tail[-4:]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def list_users_with_token() -> list[dict]:
    """Return users joined with their active-token status + FSE settings.

    status ∈ {"active", "expired", "none"}.
    Each row also carries:
      - can_use_strategy: bool
      - webhook_display:  str   (masked URL or "—")
    """
    now = _now_iso()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.name, u.created_at,
                   u.can_use_strategy,
                   u.discord_webhook_url,
                   t.id          AS token_id,
                   t.prefix      AS token_prefix,
                   t.expires_at  AS token_expires_at,
                   t.last_used_at
            FROM users u
            LEFT JOIN api_tokens t
              ON t.user_id = u.id AND t.revoked_at IS NULL
            ORDER BY u.id
            """
        ).fetchall()

    out: list[dict] = []
    for r in rows:
        d = dict(r)
        if d["token_id"] is None:
            d["token_status"] = "none"
        elif d["token_expires_at"] and d["token_expires_at"] < now:
            d["token_status"] = "expired"
        else:
            d["token_status"] = "active"
        d["can_use_strategy"] = bool(d["can_use_strategy"])
        d["webhook_display"] = _mask_webhook(d["discord_webhook_url"])
        out.append(d)
    return out


def create_user(name: str) -> int:
    """Insert a user. Raises sqlite3.IntegrityError if name exists."""
    with connect() as conn:
        cur = conn.execute("INSERT INTO users (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid


def refresh_token(
    user_id: int, label: str, expiry_days: int | None = _DEFAULT_EXPIRY_DAYS,
) -> tuple[str, int]:
    """Issue a new token for `user_id`, revoking any prior active row.

    Returns (plaintext, token_id). Plaintext is shown ONCE.
    """
    body = secrets.token_urlsafe(_TOKEN_BODY_BYTES)
    plaintext = f"{_TOKEN_PREFIX}{body}"
    digest = _hash_token(plaintext)
    display_prefix = f"{_TOKEN_PREFIX}{body[:_PREFIX_DISPLAY_LEN]}"

    expires_at = None
    if expiry_days is not None:
        expires_at = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(days=expiry_days)
        ).isoformat()

    now = _now_iso()
    with connect() as conn:
        conn.execute(
            "UPDATE api_tokens SET revoked_at = ? "
            "WHERE user_id = ? AND revoked_at IS NULL",
            (now, user_id),
        )
        cur = conn.execute(
            "INSERT INTO api_tokens "
            "(token_hash, prefix, label, user_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (digest, display_prefix, label, user_id, now, expires_at),
        )
        conn.commit()
        return plaintext, cur.lastrowid


def revoke_active_token(user_id: int) -> bool:
    """Revoke a user's active token. Returns True if a row was updated."""
    now = _now_iso()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE api_tokens SET revoked_at = ? "
            "WHERE user_id = ? AND revoked_at IS NULL",
            (now, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def set_strategy_permission(user_id: int, granted: bool) -> bool:
    """Set can_use_strategy for `user_id`. Returns True iff a row was updated."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET can_use_strategy = ? WHERE id = ?",
            (1 if granted else 0, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def set_discord_webhook(user_id: int, url: str) -> bool:
    """Validate format + persist a per-user Discord webhook.

    Raises ValueError if the URL does not look like a Discord webhook.
    Returns True iff the user row was updated.
    """
    if not _DISCORD_WEBHOOK_RE.match(url or ""):
        raise ValueError(
            "not a valid discord webhook URL "
            "(expected https://discord.com/api/webhooks/<id>/<token>)"
        )
    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET discord_webhook_url = ? WHERE id = ?",
            (url, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def clear_discord_webhook(user_id: int) -> bool:
    """Set discord_webhook_url back to NULL. Returns True iff updated."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET discord_webhook_url = NULL WHERE id = ?",
            (user_id,),
        )
        conn.commit()
        return cur.rowcount > 0
