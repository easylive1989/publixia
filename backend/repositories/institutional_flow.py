"""institutional_flow_daily repository：TWSE 每日法人原始買賣金額。"""
from db.connection import get_connection

_AMOUNT_COLUMNS = (
    "dealer_proprietary_buy", "dealer_proprietary_sell",
    "dealer_hedge_buy", "dealer_hedge_sell",
    "trust_buy", "trust_sell",
    "foreign_buy", "foreign_sell",
    "foreign_dealer_buy", "foreign_dealer_sell",
    "total_buy", "total_sell",
)


def upsert_days(market: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    payload = [{**row, "market": market} for row in rows]
    columns = ("market", "date", *_AMOUNT_COLUMNS)
    placeholders = ", ".join(f":{column}" for column in columns)
    updates = ", ".join(
        f"{column}=excluded.{column}" for column in _AMOUNT_COLUMNS
    )
    sql = (
        f"INSERT INTO institutional_flow_daily ({', '.join(columns)}) "
        f"VALUES ({placeholders}) "
        "ON CONFLICT(market, date) DO UPDATE SET "
        f"{updates}, updated_at=datetime('now')"
    )
    with get_connection() as conn:
        conn.executemany(sql, payload)
    return len(payload)


def list_days(market: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, " + ", ".join(_AMOUNT_COLUMNS) + " "
            "FROM institutional_flow_daily WHERE market = ? ORDER BY date",
            (market,),
        ).fetchall()
        return [dict(row) for row in rows]


def existing_dates(market: str) -> set[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date FROM institutional_flow_daily WHERE market = ?",
            (market,),
        ).fetchall()
        return {row["date"] for row in rows}


def notification_fingerprint(market: str, day: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT fingerprint FROM institutional_flow_notifications "
            "WHERE market = ? AND date = ?",
            (market, day),
        ).fetchone()
        return row["fingerprint"] if row else None


def record_notification(market: str, day: str, fingerprint: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO institutional_flow_notifications (market, date, fingerprint) "
            "VALUES (?, ?, ?) ON CONFLICT(market, date) DO UPDATE SET "
            "fingerprint=excluded.fingerprint, sent_at=datetime('now')",
            (market, day, fingerprint),
        )
