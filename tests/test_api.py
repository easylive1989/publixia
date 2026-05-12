import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import pytest
import db
import json

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def seed_data():
    """Seed data after conftest.py's reset_db re-initialises the DB."""
    db.save_indicator("taiex", 21458.0, json.dumps({"change_pct": 0.58, "prev_close": 21334.0}))
    db.save_indicator("fx", 32.15, json.dumps({"change_pct": 0.12, "prev_close": 32.11}))
    db.save_indicator("fear_greed", 58.0, json.dumps({"label": "貪婪"}))
    db.save_indicator("margin_balance", 2341.0, json.dumps({"unit": "億元"}))
    db.save_indicator("ndc", 24.0, json.dumps({"light": "黃紅燈", "light_code": 4}))
    db.add_watched_ticker(1, "0050.TW")
    db.save_stock_snapshot("0050.TW", 198.35, 1.15, 0.58, "TWD", "元大台灣50")


def test_dashboard_returns_all_indicators():
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    for key in ["taiex", "fx", "fear_greed", "margin_balance", "ndc"]:
        assert key in data
        assert "value" in data[key]
        assert "timestamp" in data[key]


def test_dashboard_includes_next_update_at_per_indicator():
    """Each indicator slot exposes the next scheduled update time so the
    frontend can render '下次更新 …' on each card. The scheduler isn't
    started in tests, so we seed the rows the way it would on boot."""
    from repositories.scheduler import insert_default
    insert_default("taiex", "0 14 * * *")
    insert_default("chip_total", "0 18 * * *")

    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "next_update_at" in data["taiex"]
    assert data["taiex"]["next_update_at"] is not None
    # ISO 8601 with offset, e.g. "2026-05-08T14:00:00+08:00".
    assert "T" in data["taiex"]["next_update_at"]
    # margin_balance is wired to the chip_total job, which we seeded above.
    assert data["margin_balance"]["next_update_at"] is not None
    assert "T" in data["margin_balance"]["next_update_at"]
    # Indicators whose job has no row return None instead of crashing.
    assert data["fx"]["next_update_at"] is None


def test_history_returns_list():
    r = client.get("/api/history/taiex?time_range=3M")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert rows[0]["value"] == 21458.0


def test_history_unknown_indicator_returns_404():
    r = client.get("/api/history/unknown")
    assert r.status_code == 404


def test_history_is_one_row_per_trading_date():
    """Daily-snapshot guarantee: regardless of how many times the fetcher writes
    on the same date, /api/history returns one row per date, ordered chronologically."""
    from datetime import datetime, timedelta, timezone
    base = datetime.now(timezone.utc).replace(tzinfo=None)

    # Three writes on 'today' — all upsert into the same (taiex, today) row.
    db.save_indicator("taiex", 39000.0, timestamp=base - timedelta(hours=4))
    db.save_indicator("taiex", 39200.0, timestamp=base - timedelta(hours=2))
    db.save_indicator("taiex", 39303.5, timestamp=base)
    # One write yesterday — a separate row.
    db.save_indicator("taiex", 38900.0, timestamp=base - timedelta(days=1))
    # Day before yesterday — another separate row.
    db.save_indicator("taiex", 38500.0, timestamp=base - timedelta(days=2))

    r = client.get("/api/history/taiex?time_range=1M")
    assert r.status_code == 200
    rows = r.json()
    # Exactly 3 rows for 3 distinct dates (the seed_data write today is also
    # on `today`, so it gets upserted into the same row as our 3 writes above).
    dates = [row["timestamp"][:10] for row in rows]
    assert len(dates) == len(set(dates)), f"duplicate dates in history: {dates}"
    # Ordered ascending by timestamp.
    assert dates == sorted(dates)
    # The latest row for 'today' won (39303.5), not the earlier ones.
    assert rows[-1]["value"] == 39303.5


def test_get_stocks_returns_watchlist():
    r = client.get("/api/stocks")
    assert r.status_code == 200
    stocks = r.json()
    tickers = [s["ticker"] for s in stocks]
    assert "0050.TW" in tickers


def test_add_and_delete_stock():
    r = client.post("/api/stocks", json={"ticker": "2330.tw"})
    assert r.status_code == 200
    tickers = db.get_watched_tickers(1)
    assert "2330.TW" in tickers  # normalized to uppercase

    r = client.delete("/api/stocks/2330.TW")
    assert r.status_code == 200
    assert "2330.TW" not in db.get_watched_tickers(1)


def test_stock_history_returns_data(monkeypatch):
    fake = {
        "ticker": "2330.TW",
        "name": "台積電",
        "currency": "TWD",
        "time_range": "3M",
        "dates": ["2026-01-02", "2026-01-03"],
        "candles": [
            {"open": 700, "high": 710, "low": 695, "close": 705, "volume": 12345},
            {"open": 705, "high": 715, "low": 700, "close": 710, "volume": 23456},
        ],
        "indicators": {
            "ma5": [None, None],
            "ma20": [None, None],
            "ma60": [None, None],
            "rsi14": [50.0, 60.0],
            "macd": [0.1, 0.2],
            "macd_signal": [0.05, 0.1],
            "macd_histogram": [0.05, 0.1],
        },
    }
    monkeypatch.setattr("api.routes.stocks.fetch_stock_history", lambda ticker, time_range: fake)
    db.add_watched_ticker(1, "2330.TW")
    r = client.get("/api/stocks/2330.tw/history?time_range=3M")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "2330.TW"
    assert len(data["candles"]) == 2
    assert "rsi14" in data["indicators"]


def test_stock_history_404_when_no_data(monkeypatch):
    monkeypatch.setattr("api.routes.stocks.fetch_stock_history", lambda ticker, time_range: None)
    r = client.get("/api/stocks/UNKNOWN/history?time_range=3M")
    assert r.status_code == 404


def test_stock_history_rejects_invalid_range():
    db.add_watched_ticker(1, "2330.TW")
    r = client.get("/api/stocks/2330.TW/history?time_range=10Y")
    assert r.status_code == 400


def test_refresh_unknown_indicator_returns_404():
    r = client.post("/api/refresh/bogus")
    assert r.status_code == 404


def test_endpoint_returns_401_without_auth_override():
    """Without dependency_override, endpoints require Authorization header."""
    from api.dependencies import require_token

    saved = app.dependency_overrides.pop(require_token, None)
    try:
        unauthed = TestClient(app)
        r = unauthed.get("/api/dashboard")
        assert r.status_code == 401
        assert "Missing" in r.json()["detail"] or "Invalid" in r.json()["detail"]
    finally:
        if saved is not None:
            app.dependency_overrides[require_token] = saved


def test_detail_404_when_not_in_watchlist():
    r = client.get("/api/stocks/UNKNOWN.XYZ/history?time_range=1M")
    assert r.status_code == 404
    r = client.get("/api/stocks/UNKNOWN.XYZ/valuation")
    assert r.status_code == 404
    r = client.get("/api/stocks/UNKNOWN.XYZ/revenue")
    assert r.status_code == 404
    r = client.get("/api/stocks/UNKNOWN.XYZ/financial")
    assert r.status_code == 404
    r = client.get("/api/stocks/UNKNOWN.XYZ/dividend")
    assert r.status_code == 404


def test_detail_passes_gate_for_user_watchlist():
    """A ticker works once the user adds it to their personal watchlist."""
    db.add_watched_ticker(1, "FAKE.US")
    r = client.get("/api/stocks/FAKE.US/dividend")
    # FAKE.US is NOT a Taiwan ticker → fundamentals routes 400 (not 404 from gating)
    assert r.status_code != 404
