"""Schema checks for the foreign-futures-flow feature migrations."""
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


def test_institutional_futures_daily_schema():
    assert _table_exists("institutional_futures_daily")
    cols = _columns("institutional_futures_daily")
    for name in (
        "symbol", "date",
        "foreign_long_oi", "foreign_short_oi",
        "foreign_long_amount", "foreign_short_amount",
    ):
        assert name in cols, f"missing column {name}"
    # symbol+date are the composite PK.
    pk = sorted(c["name"] for c in cols.values() if c["pk"])
    assert pk == ["date", "symbol"]


def test_futures_settlement_dates_schema():
    assert _table_exists("futures_settlement_dates")
    cols = _columns("futures_settlement_dates")
    for name in ("symbol", "year_month", "settlement_date"):
        assert name in cols, f"missing column {name}"
