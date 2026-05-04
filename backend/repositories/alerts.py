"""Price-alert repository."""
from datetime import datetime, timezone

from db.connection import get_connection


def list_alerts(user_id: int | None = None) -> list[dict]:
    """Return alerts.

    Pass `user_id` to scope to one user (used by the API route).
    Pass `None` (or omit) for the global list — used by the alert
    engine, which evaluates every alert regardless of user.
    """
    with get_connection() as conn:
        if user_id is None:
            rows = conn.execute(
                "SELECT * FROM price_alerts ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM price_alerts WHERE user_id=? "
                "ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def add_alert(user_id: int, target_type: str, target: str,
              condition: str, threshold: float,
              *, indicator_key: str | None = None,
              window_n: int | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO price_alerts "
            "(user_id, target_type, target, condition, threshold, "
            " indicator_key, window_n, enabled, created_at) "
            "VALUES (?,?,?,?,?,?,?,1,?)",
            (user_id, target_type, target, condition, threshold,
             indicator_key, window_n,
             datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        )
        return cur.lastrowid


def delete_alert(user_id: int, alert_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM price_alerts WHERE id=? AND user_id=?",
            (alert_id, user_id),
        )


def set_alert_enabled(user_id: int, alert_id: int, enabled: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE price_alerts SET enabled=?, "
            "       triggered_at=NULL, triggered_value=NULL "
            "WHERE id=? AND user_id=?",
            (1 if enabled else 0, alert_id, user_id),
        )


def get_active_alerts(target_type: str, target: str) -> list[dict]:
    """Engine-side: returns active alerts for any user matching this
    (target_type, target). Used by alert_engine to fire notifications
    for every user that subscribed."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM price_alerts WHERE target_type=? AND target=? AND enabled=1",
            (target_type, target),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_alert_triggered(alert_id: int, value: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE price_alerts SET enabled=0, triggered_at=?, triggered_value=? WHERE id=?",
            (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), value, alert_id),
        )
