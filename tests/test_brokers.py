from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from fetchers.broker import _aggregate, to_finmind_id, fetch_broker_daily

client = TestClient(app)


def test_to_finmind_id_strips_suffix():
    assert to_finmind_id("2330.TW") == "2330"
    assert to_finmind_id("6488.TWO") == "6488"
    assert to_finmind_id("2330") == "2330"
    assert to_finmind_id("AAPL") is None
    assert to_finmind_id("") is None


def test_aggregate_sums_buy_sell_per_broker_per_day():
    raw = [
        {"date": "2026-04-28", "securities_trader_id": "9100",
         "securities_trader": "永豐金", "price": 100.0, "buy": 10, "sell": 2},
        {"date": "2026-04-28", "securities_trader_id": "9100",
         "securities_trader": "永豐金", "price": 101.0, "buy": 5,  "sell": 0},
        {"date": "2026-04-28", "securities_trader_id": "9200",
         "securities_trader": "凱基",   "price": 100.0, "buy": 0,  "sell": 8},
    ]
    out = _aggregate(raw, "2330.TW")
    by_id = {r["securities_trader_id"]: r for r in out}
    assert by_id["9100"]["buy_volume"] == 15
    assert by_id["9100"]["sell_volume"] == 2
    # weighted: 10*100 + 5*101 = 1505
    assert by_id["9100"]["buy_amount"] == 1505
    assert by_id["9200"]["sell_volume"] == 8


def test_brokers_endpoint_empty_when_no_data():
    # 2330.TW is in the auto-tracked seed list so the watchlist gate passes.
    # The endpoint is intentionally stubbed (FinMind dataset went sponsor-
    # only) — it always returns ok=False with no rows.
    with patch("fetchers.broker.fetch_broker_daily", return_value=False):
        r = client.get("/api/stocks/2330.TW/brokers")
    assert r.status_code == 200
    body = r.json()
    assert body["top_brokers"] == []
    assert body["as_of"] is None


def test_fetch_broker_daily_skips_non_tw():
    assert fetch_broker_daily("AAPL") is False
