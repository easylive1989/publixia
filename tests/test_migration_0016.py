"""Schema checks for migration 0016 (txo_strike_oi_daily)."""
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


def _indexes(table: str) -> list[str]:
    rows = db.connection.get_connection().execute(
        f"PRAGMA index_list({table})"
    ).fetchall()
    return [r["name"] for r in rows]


def test_txo_strike_oi_daily_schema():
    assert _table_exists("txo_strike_oi_daily")
    cols = _columns("txo_strike_oi_daily")
    for name in (
        "symbol", "date", "expiry_month", "strike", "put_call",
        "open_interest", "settle_price",
    ):
        assert name in cols, f"missing column {name}"
    # PK is the 5-tuple (symbol, date, expiry_month, strike, put_call).
    pk = sorted(c["name"] for c in cols.values() if c["pk"])
    assert pk == ["date", "expiry_month", "put_call", "strike", "symbol"]
    # settle_price is the only nullable column.
    assert cols["settle_price"]["notnull"] == 0
    assert cols["open_interest"]["notnull"] == 1


def test_txo_strike_oi_daily_has_date_index():
    idx = _indexes("txo_strike_oi_daily")
    assert "idx_txo_strike_oi_date" in idx
    assert "idx_txo_strike_oi_date_expiry" in idx
