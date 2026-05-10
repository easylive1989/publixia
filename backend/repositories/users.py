"""Users repository."""
from typing import Optional

from db.connection import get_connection


def create_user(name: str) -> int:
    """Insert a user. Raises sqlite3.IntegrityError if name already exists."""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO users (name) VALUES (?)",
        (name,),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_id(user_id: int) -> Optional[dict]:
    row = get_connection().execute(
        "SELECT id, name, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_name(name: str) -> Optional[dict]:
    row = get_connection().execute(
        "SELECT id, name, created_at FROM users WHERE name = ?",
        (name,),
    ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    rows = get_connection().execute(
        "SELECT id, name, created_at FROM users ORDER BY id",
    ).fetchall()
    return [dict(r) for r in rows]


def get_user_with_settings(user_id: int) -> Optional[dict]:
    """Like get_user_by_id but also returns FSE-related columns.

    Booleans are decoded from SQLite's INTEGER 0/1 to Python bool so callers
    don't have to remember the underlying storage.

    SECURITY: the returned dict includes the raw `discord_webhook_url`
    plaintext. Do NOT splat this dict (`**user`) into a public response
    model — only the backend notifier (P4+) is allowed to read it. Public
    endpoints must derive `has_webhook = url is not None` and discard the
    URL itself, as `api/routes/me.py` does.
    """
    row = get_connection().execute(
        "SELECT id, name, created_at, "
        "       can_use_strategy, can_view_top100, can_view_foreign_futures, "
        "       discord_webhook_url "
        "FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["can_use_strategy"] = bool(d["can_use_strategy"])
    d["can_view_top100"] = bool(d["can_view_top100"])
    d["can_view_foreign_futures"] = bool(d["can_view_foreign_futures"])
    return d


def set_strategy_permission(user_id: int, granted: bool) -> bool:
    """Set can_use_strategy to `granted`. Returns True iff a row was updated."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET can_use_strategy = ? WHERE id = ?",
        (1 if granted else 0, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def set_top100_permission(user_id: int, granted: bool) -> bool:
    """Set can_view_top100 to `granted`. Returns True iff a row was updated."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET can_view_top100 = ? WHERE id = ?",
        (1 if granted else 0, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def set_foreign_futures_permission(user_id: int, granted: bool) -> bool:
    """Set can_view_foreign_futures to `granted`. Returns True iff updated."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET can_view_foreign_futures = ? WHERE id = ?",
        (1 if granted else 0, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def set_discord_webhook(user_id: int, url: str) -> bool:
    """Store a per-user webhook (plaintext). Returns True iff updated.

    Callers are responsible for validating the URL format before calling
    this function — admin/ops.py owns the regex check today.
    """
    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET discord_webhook_url = ? WHERE id = ?",
        (url, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def clear_discord_webhook(user_id: int) -> bool:
    """Set discord_webhook_url back to NULL. Returns True iff updated."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET discord_webhook_url = NULL WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    return cur.rowcount > 0
