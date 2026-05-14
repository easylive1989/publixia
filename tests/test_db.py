import db


def test_init_creates_core_tables():
    db.init_db()
    conn = db.get_connection()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert {
        "indicator_snapshots",
        "futures_daily",
        "institutional_futures_daily",
        "institutional_options_daily",
        "txo_strike_oi_daily",
        "tx_large_trader_daily",
        "foreign_flow_ai_reports",
        "scheduler_jobs",
    } <= tables


def test_purged_tables_are_gone():
    """All per-user and per-stock tables were dropped in migration 0019/0020."""
    db.init_db()
    conn = db.get_connection()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    for t in (
        "users", "api_tokens", "price_alerts", "watched_stocks",
        "stock_snapshots", "stock_broker_daily", "stock_chip_daily",
        "stock_per_daily", "stock_revenue_monthly",
        "stock_financial_quarterly", "stock_dividend_history",
        "strategies", "strategy_signals",
    ):
        assert t not in tables, f"{t} should have been dropped"


def test_init_db_creates_schema_migrations_with_0001_applied():
    db.init_db()
    versions = [r[0] for r in db.get_connection().execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()]
    assert "0001" in versions


def test_save_and_get_indicator():
    db.init_db()
    db.save_indicator("taiex", 21458.0, '{"change_pct": 0.58}')
    row = db.get_latest_indicator("taiex")
    assert row is not None
    assert row["value"] == 21458.0
    assert row["indicator"] == "taiex"


def test_get_indicator_returns_none_when_empty():
    db.init_db()
    assert db.get_latest_indicator("ndc") is None


def test_indicator_history_filtered_by_date():
    db.init_db()
    from datetime import datetime, timedelta, timezone
    # Two writes on the same date should upsert into one row (latest wins).
    db.save_indicator("margin_balance", 2500.0)
    db.save_indicator("margin_balance", 2341.0)
    # A write on a different (earlier) date stays as a separate row.
    db.save_indicator(
        "margin_balance",
        2200.0,
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
    )
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
    rows = db.get_indicator_history("margin_balance", since)
    assert len(rows) == 2
    assert rows[-1]["value"] == 2341.0  # today's latest upsert wins
