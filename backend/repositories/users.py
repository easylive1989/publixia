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
    """Like get_user_by_id but also returns per-user feature flags.

    Booleans are decoded from SQLite's INTEGER 0/1 to Python bool so
    callers don't have to remember the underlying storage.
    """
    row = get_connection().execute(
        "SELECT id, name, created_at, can_view_foreign_futures "
        "FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["can_view_foreign_futures"] = bool(d["can_view_foreign_futures"])
    return d


def set_foreign_futures_permission(user_id: int, granted: bool) -> bool:
    """Set can_view_foreign_futures to `granted`. Returns True iff updated."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET can_view_foreign_futures = ? WHERE id = ?",
        (1 if granted else 0, user_id),
    )
    conn.commit()
    return cur.rowcount > 0
