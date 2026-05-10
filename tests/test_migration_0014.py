"""Schema check for migration 0014 (tx_large_trader_daily)."""
import db


def _columns(table: str) -> dict[str, dict]:
    rows = db.connection.get_connection().execute(
        f"PRAGMA table_info({table})"
    ).fetchall()
    return {r["name"]: dict(r) for r in rows}


def _table_exists(name: str) -> bool:
    row = db.connection.get_connection().execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def test_tx_large_trader_daily_schema():
    assert _table_exists("tx_large_trader_daily")
    cols = _columns("tx_large_trader_daily")
    for name in (
        "date", "market_oi",
        "top5_long_oi",  "top5_short_oi",
        "top10_long_oi", "top10_short_oi",
    ):
        assert name in cols, f"missing column {name}"
    # date is the primary key.
    pk = sorted(c["name"] for c in cols.values() if c["pk"])
    assert pk == ["date"]
