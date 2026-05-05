"""Taiwan index futures (TX) fetcher + route tests."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import db
from main import app
from fetchers.futures import parse_front_month, fetch_tw_futures, SYMBOL

client = TestClient(app)


# 模擬 FinMind TaiwanFuturesDaily 回傳:同一天有多個合約月,且包含一般/夜盤
SAMPLE_RAW = [
    # 2026-04-29 三檔合約 + 一筆夜盤 — 應選成交量最大者
    {"date": "2026-04-29", "futures_id": "TX", "contract_date": "202605",
     "trading_session": "position", "open": 21000, "max": 21100, "min": 20950, "close": 21080,
     "volume": 80000, "settlement_price": 21075, "open_interest": 50000},
    {"date": "2026-04-29", "futures_id": "TX", "contract_date": "202606",
     "trading_session": "position", "open": 20990, "max": 21090, "min": 20940, "close": 21070,
     "volume": 12000, "settlement_price": 21065, "open_interest": 8000},
    {"date": "2026-04-29", "futures_id": "TX", "contract_date": "202607",
     "trading_session": "position", "open": 20980, "max": 21080, "min": 20930, "close": 21060,
     "volume": 5000,  "settlement_price": 21055, "open_interest": 3000},
    {"date": "2026-04-29", "futures_id": "TX", "contract_date": "202605",
     "trading_session": "after_market", "open": 21080, "max": 21120, "min": 21050, "close": 21090,
     "volume": 30000, "settlement_price": None, "open_interest": 50000},
    # 2026-04-30 兩檔 — 主力換到下一個月
    {"date": "2026-04-30", "futures_id": "TX", "contract_date": "202605",
     "trading_session": "position", "open": 21080, "max": 21150, "min": 21040, "close": 21120,
     "volume": 60000, "settlement_price": 21118, "open_interest": 45000},
    {"date": "2026-04-30", "futures_id": "TX", "contract_date": "202606",
     "trading_session": "position", "open": 21070, "max": 21140, "min": 21030, "close": 21110,
     "volume": 70000, "settlement_price": 21108, "open_interest": 47000},
    # 零成交合約應被略過
    {"date": "2026-04-30", "futures_id": "TX", "contract_date": "202612",
     "trading_session": "position", "open": None, "max": None, "min": None, "close": None,
     "volume": 0, "settlement_price": None, "open_interest": 0},
]


def test_parse_front_month_picks_highest_volume_day_session():
    out = parse_front_month(SAMPLE_RAW)
    by_date = {r["date"]: r for r in out}
    assert set(by_date) == {"2026-04-29", "2026-04-30"}

    # 2026-04-29:成交量最大的是 202605(80000),夜盤(after_market 30000)應被排除
    d29 = by_date["2026-04-29"]
    assert d29["contract_date"] == "202605"
    assert d29["close"] == 21080
    assert d29["volume"] == 80000
    assert d29["high"] == 21100
    assert d29["low"]  == 20950

    # 2026-04-30:202606 成交量反超為 70000
    d30 = by_date["2026-04-30"]
    assert d30["contract_date"] == "202606"
    assert d30["close"] == 21110
    assert d30["volume"] == 70000


def test_parse_front_month_ignores_zero_volume():
    rows = [{
        "date": "2026-05-02", "futures_id": "TX", "contract_date": "202605",
        "trading_session": "position", "open": 0, "max": 0, "min": 0, "close": 0,
        "volume": 0, "settlement_price": None, "open_interest": 0,
    }]
    assert parse_front_month(rows) == []


def test_fetch_tw_futures_writes_repo_and_indicator():
    db.init_db()
    with patch("fetchers.futures._request", return_value=SAMPLE_RAW):
        ok = fetch_tw_futures()
    assert ok is True

    # futures_daily upserted
    rows = db.get_futures_daily_range(SYMBOL, "2026-01-01")
    assert [r["date"] for r in rows] == ["2026-04-29", "2026-04-30"]
    assert rows[1]["close"] == 21110

    # indicator_snapshots also written so dashboard sparkline picks it up
    latest = db.get_latest_indicator("tw_futures")
    assert latest is not None
    assert latest["value"] == 21110
    # change_pct = (21110 - 21080) / 21080 * 100 ≈ 0.14
    import json
    extra = json.loads(latest["extra_json"])
    assert extra["prev_close"] == 21080
    assert extra["change_pct"] == pytest.approx(0.14, abs=0.01)


def test_fetch_tw_futures_lazy_skip_when_up_to_date():
    db.init_db()
    # Seed today's data so fetcher should skip the network call.
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).astimezone().date().strftime("%Y-%m-%d")
    db.save_futures_daily_rows([{
        "symbol": SYMBOL, "date": today, "contract_date": "202506",
        "open": 1, "high": 1, "low": 1, "close": 1,
        "volume": 1, "open_interest": 1, "settlement": 1,
    }])
    called = {"n": 0}

    def boom(*a, **kw):
        called["n"] += 1
        raise AssertionError("should not call network")

    with patch("fetchers.futures._request", side_effect=boom):
        ok = fetch_tw_futures()
    assert ok is True
    assert called["n"] == 0


def test_dashboard_includes_tw_futures():
    db.init_db()
    db.save_indicator(
        "tw_futures", 21100,
        '{"change_pct": 0.5, "prev_close": 21000, "contract": "202506"}',
        date="2026-05-02",
    )
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    payload = r.json()
    assert payload["tw_futures"]["value"] == 21100
    assert payload["tw_futures"]["extra"]["contract"] == "202506"


def test_futures_history_endpoint_returns_ohlcv_and_indicators():
    db.init_db()
    # Seed enough rows to compute MA/MACD — reuse SAMPLE_RAW pipeline.
    with patch("fetchers.futures._request", return_value=SAMPLE_RAW):
        fetch_tw_futures()
    r = client.get("/api/futures/tw/history?time_range=3M")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "TX"
    assert body["dates"][-1] == "2026-04-30"
    assert body["candles"][-1]["close"] == 21110
    # indicators always have the same length as dates
    assert len(body["indicators"]["macd"]) == len(body["dates"])


def test_futures_history_404_when_empty():
    db.init_db()
    with patch("fetchers.futures._request", return_value=[]):
        r = client.get("/api/futures/tw/history?time_range=3M")
    assert r.status_code == 404
