"""Schema checks for migration 0015 (institutional_options_daily)."""
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


def test_institutional_options_daily_schema():
    assert _table_exists("institutional_options_daily")
    cols = _columns("institutional_options_daily")
    for name in (
        "symbol", "date", "identity", "put_call",
        "long_oi", "short_oi", "long_amount", "short_amount",
    ):
        assert name in cols, f"missing column {name}"
    # PK is the 4-tuple (symbol, date, identity, put_call) so a single
    # day produces 6 rows per product (3 identities × CALL/PUT).
    pk = sorted(c["name"] for c in cols.values() if c["pk"])
    assert pk == ["date", "identity", "put_call", "symbol"]
