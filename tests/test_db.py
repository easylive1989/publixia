import pytest
import db

def test_init_creates_tables():
    db.init_db()
    conn = db.get_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"indicator_snapshots", "watched_stocks", "stock_snapshots"} <= tables

def test_init_db_creates_schema_migrations_with_0001_applied():
    """init_db() now goes through the migration runner."""
    db.init_db()
    versions = [r[0] for r in db.get_connection().execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()]
    assert "0001" in versions

def test_init_db_baselines_existing_legacy_db():
    """Simulate the live VPS DB: it already has the post-0001 schema but
    no schema_migrations. init_db() must baseline 0001 (skip re-run) AND
    apply 0002+ normally so new tables/columns from later migrations appear."""
    import os
    db.connection._memory_conn = None
    conn = db.get_connection()
    here = os.path.dirname(__file__)
    sql_path = os.path.join(here, "..", "backend", "db", "migrations", "0001_initial.sql")
    with open(sql_path, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.execute(
        "INSERT INTO indicator_snapshots (indicator, timestamp, value) "
        "VALUES ('taiex', '2026-01-01T00:00:00', 17000.0)"
    )
    conn.commit()

    db.init_db()  # should baseline, not re-run

    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()]
    assert "0001" in versions
    # Original row preserved.
    rows = conn.execute(
        "SELECT indicator, value FROM indicator_snapshots"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [("taiex", 17000.0)]

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

def test_watched_stocks_crud():
    db.init_db()
    db.add_watched_ticker(1, "2330.TW")
    db.add_watched_ticker(1, "VOO")
    tickers = db.get_watched_tickers(1)
    assert "2330.TW" in tickers
    assert "VOO" in tickers
    db.remove_watched_ticker(1, "VOO")
    assert "VOO" not in db.get_watched_tickers(1)

def test_add_duplicate_ticker_is_idempotent():
    db.init_db()
    db.add_watched_ticker(1, "AAPL")
    db.add_watched_ticker(1, "AAPL")
    assert db.get_watched_tickers(1).count("AAPL") == 1

def test_save_and_get_stock_snapshot():
    db.init_db()
    db.add_watched_ticker(1, "0050.TW")
    db.save_stock_snapshot("0050.TW", 198.35, 1.15, 0.58, "TWD", "元大台灣50")
    row = db.get_latest_stock("0050.TW")
    assert row["price"] == 198.35
    assert row["name"] == "元大台灣50"


def test_alert_crud_and_lifecycle():
    db.init_db()
    aid = db.add_alert(1, "indicator", "taiex", "above", 22000.0)
    assert aid > 0

    alerts = db.list_alerts()
    assert len(alerts) == 1
    assert alerts[0]["target"] == "taiex"
    assert alerts[0]["enabled"] == 1

    active = db.get_active_alerts("indicator", "taiex")
    assert len(active) == 1

    db.mark_alert_triggered(aid, 22150.5)
    after = db.list_alerts()[0]
    assert after["enabled"] == 0
    assert after["triggered_value"] == 22150.5
    assert after["triggered_at"] is not None
    assert db.get_active_alerts("indicator", "taiex") == []

    db.set_alert_enabled(1, aid, True)
    re_armed = db.list_alerts()[0]
    assert re_armed["enabled"] == 1
    assert re_armed["triggered_at"] is None

    db.delete_alert(1, aid)
    assert db.list_alerts() == []


def test_remove_watched_ticker_disables_stock_indicator_alerts():
    """移除 watchlist ticker 應同時停用該 ticker 的 stock_indicator alerts(Phase 4 follow-up)。"""
    db.init_db()
    db.add_watched_ticker(1, "2330.TW")
    a1 = db.add_alert(1, "stock_indicator", "2330.TW", "above", 30,
                      indicator_key="per", window_n=None)
    a2 = db.add_alert(1, "indicator", "margin_balance", "above", 5000,
                      indicator_key=None, window_n=None)
    a3 = db.add_alert(1, "stock_indicator", "2454.TW", "above", 50,
                      indicator_key="per", window_n=None)

    db.remove_watched_ticker(1, "2330.TW")

    alerts = {a["id"]: a for a in db.list_alerts()}
    assert alerts[a1]["enabled"] == 0
    assert alerts[a2]["enabled"] == 1
    assert alerts[a3]["enabled"] == 1


def test_remove_watched_ticker_does_not_affect_stock_price_alerts():
    """移除 ticker 不應該動到 'stock' (價格)類型 alerts — 跟 stock_indicator 分開處理。"""
    db.init_db()
    db.add_watched_ticker(1, "2330.TW")
    a1 = db.add_alert(1, "stock", "2330.TW", "above", 1000)

    db.remove_watched_ticker(1, "2330.TW")

    alerts = {a["id"]: a for a in db.list_alerts()}
    assert alerts[a1]["enabled"] == 1


def test_seed_loader_is_idempotent():
    """init_db() seeds auto-tracked once; running it again does not duplicate."""
    from repositories.auto_tracked import list_auto_tracked_tickers
    before = set(list_auto_tracked_tickers())
    assert len(before) >= 80, f"seed should yield ≥80 tickers, got {len(before)}"
    db.init_db()
    after = set(list_auto_tracked_tickers())
    assert before == after


def test_global_watched_tickers_includes_auto_tracked():
    """get_watched_tickers(None) is the union used by background fetchers."""
    db.add_watched_ticker(1, 'TSTUSER.TW')
    auto = db.get_watched_tickers()
    # Seed list includes 2330.TW
    assert '2330.TW' in auto
    # User's personal addition also surfaces
    assert 'TSTUSER.TW' in auto


def test_user_watchlist_excludes_auto_tracked():
    """get_watched_tickers(user_id) returns ONLY that user's personal list."""
    db.add_watched_ticker(1, 'TSTONLY.TW')
    user_only = db.get_watched_tickers(1)
    assert 'TSTONLY.TW' in user_only
    # Auto-tracked seed shouldn't bleed into the user's personal view.
    assert '2330.TW' not in user_only
