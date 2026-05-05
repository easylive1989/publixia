"""Scheduler job configuration repository.

Backs the `scheduler_jobs` table. Used by:
- `backend/scheduler.py` on startup to read cron / enabled, and at job
  end to record run status
- the admin CLI (which talks to SQLite directly) to list and edit
  schedules — see `admin/scheduler_ops.py`
"""
from datetime import datetime, timezone

from db.connection import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def list_jobs() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name, cron_expr, enabled, last_run_at, last_status, "
            "       last_error, updated_at "
            "FROM scheduler_jobs ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]


def get_job(name: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT name, cron_expr, enabled, last_run_at, last_status, "
            "       last_error, updated_at "
            "FROM scheduler_jobs WHERE name = ?",
            (name,),
        ).fetchone()
        return dict(row) if row else None


def insert_default(name: str, cron_expr: str) -> bool:
    """Insert a default row for `name` if it does not yet exist.

    Returns True if a row was inserted (i.e. this is the first time we've
    seen the job), False if a user-customised row already exists.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO scheduler_jobs "
            "(name, cron_expr, enabled, updated_at) VALUES (?, ?, 1, ?)",
            (name, cron_expr, _now_iso()),
        )
        return cur.rowcount > 0


def update_cron(name: str, cron_expr: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE scheduler_jobs SET cron_expr = ?, updated_at = ? "
            "WHERE name = ?",
            (cron_expr, _now_iso(), name),
        )
        return cur.rowcount > 0


def set_enabled(name: str, enabled: bool) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE scheduler_jobs SET enabled = ?, updated_at = ? "
            "WHERE name = ?",
            (1 if enabled else 0, _now_iso(), name),
        )
        return cur.rowcount > 0


def record_run(name: str, status: str, error: str | None = None) -> None:
    """Stamp a job's last_run_at / last_status. Best-effort — never raises."""
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE scheduler_jobs SET last_run_at = ?, last_status = ?, "
                "       last_error = ? WHERE name = ?",
                (_now_iso(), status, error, name),
            )
    except Exception:
        pass
