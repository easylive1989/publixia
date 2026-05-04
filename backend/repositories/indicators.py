"""Indicator snapshot repository."""
from datetime import datetime, timezone

from db.connection import get_connection


def save_indicator(
    indicator: str,
    value: float,
    extra_json: str = None,
    timestamp: datetime = None,
    date: str = None,
):
    """Upsert one row per (indicator, date).

    `date` defaults to the date portion of `timestamp` (or now). Caller can
    pass an explicit trading-date string when the snapshot does not correspond
    to "today" — e.g. fetched on a holiday but representing the previous
    trading day's close.
    """
    ts_dt = timestamp or datetime.now(timezone.utc).replace(tzinfo=None)
    ts = ts_dt.isoformat()
    d = date or ts[:10]
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO indicator_snapshots (indicator, timestamp, value, extra_json, date) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(indicator, date) DO UPDATE SET "
            "  timestamp=excluded.timestamp, "
            "  value=excluded.value, "
            "  extra_json=excluded.extra_json",
            (indicator, ts, value, extra_json, d),
        )


def get_latest_indicator(indicator: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM indicator_snapshots WHERE indicator=? ORDER BY timestamp DESC LIMIT 1",
            (indicator,),
        ).fetchone()
        return dict(row) if row else None


def get_indicator_history(indicator: str, since: datetime) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT timestamp, value, extra_json FROM indicator_snapshots "
            "WHERE indicator=? AND timestamp>=? ORDER BY timestamp",
            (indicator, since.isoformat()),
        ).fetchall()
        return [dict(r) for r in rows]
