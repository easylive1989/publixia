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
    trading day's close, or backfilling years of historical data.

    When the caller passes `date` but no `timestamp`, the trading date is the
    source of truth: derive timestamp from it (midnight) instead of "now".
    Otherwise a bulk backfill stamps every row with insertion-time, breaking
    any reader that orders/filters by timestamp.
    """
    if timestamp is not None:
        ts_dt = timestamp
    elif date is not None:
        ts_dt = datetime.fromisoformat(date)
    else:
        ts_dt = datetime.now(timezone.utc).replace(tzinfo=None)
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
    """Return one row per trading day, ordered chronologically.

    Filter + order use `date` (the trading-day source of truth). `timestamp`
    on these rows is the wall clock when the row was first written and can be
    very wrong for bulk-backfilled data (every historical row stamped with
    "today" when the fetcher first ran).
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, value, extra_json FROM indicator_snapshots "
            "WHERE indicator=? AND date>=? ORDER BY date",
            (indicator, since.strftime("%Y-%m-%d")),
        ).fetchall()
        return [dict(r) for r in rows]
