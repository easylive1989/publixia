from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

import db
from main import app
from fetchers.broker import _aggregate, to_finmind_id, fetch_broker_daily

client = TestClient(app)


def _seed_broker_rows(ticker: str, days: list[str], rows_per_day: list[list[dict]]) -> None:
    """Helper: seed pre-aggregated broker rows directly into DB."""
    flat = []
    for d, daily in zip(days, rows_per_day):
        for r in daily:
            flat.append({
                "ticker": ticker,
                "date": d,
                "securities_trader_id": r["id"],
                "securities_trader": r.get("name", r["id"]),
                "buy_volume": r.get("buy_volume", 0),
                "sell_volume": r.get("sell_volume", 0),
                "buy_amount": r.get("buy_amount", 0),
                "sell_amount": r.get("sell_amount", 0),
            })
    db.save_broker_daily_rows(flat)


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


def test_brokers_endpoint_rejects_non_taiwan_ticker():
    r = client.get("/api/stocks/AAPL/brokers")
    assert r.status_code == 400


def test_brokers_endpoint_rejects_invalid_params():
    assert client.get("/api/stocks/2330.TW/brokers?days=999").status_code == 400
    assert client.get("/api/stocks/2330.TW/brokers?top=0").status_code == 400


def test_brokers_endpoint_returns_top5_by_net_buy():
    today = date.today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(4, -1, -1)]
    # Day-by-day rows: broker A buys consistently (net+), B sells, C buys big once
    rows_per_day = []
    for i, _ in enumerate(days):
        rows_per_day.append([
            {"id": "A", "name": "A券商", "buy_volume": 100, "sell_volume": 20,
             "buy_amount": 100 * 50.0,  "sell_amount": 20 * 50.0},
            {"id": "B", "name": "B券商", "buy_volume": 10,  "sell_volume": 200,
             "buy_amount": 10 * 50.0,   "sell_amount": 200 * 50.0},
            {"id": "C", "name": "C券商",
             "buy_volume": 500 if i == 4 else 0,
             "sell_volume": 0,
             "buy_amount": 500 * 51.0 if i == 4 else 0,
             "sell_amount": 0},
            {"id": "D", "name": "D券商", "buy_volume": 5, "sell_volume": 0,
             "buy_amount": 5 * 50.0, "sell_amount": 0},
            {"id": "E", "name": "E券商", "buy_volume": 3, "sell_volume": 0,
             "buy_amount": 3 * 50.0, "sell_amount": 0},
            {"id": "F", "name": "F券商", "buy_volume": 1, "sell_volume": 0,
             "buy_amount": 1 * 50.0, "sell_amount": 0},
        ])
    _seed_broker_rows("2330.TW", days, rows_per_day)

    # Patch fetch_broker_daily so the endpoint doesn't hit network
    with patch("fetchers.broker.fetch_broker_daily", return_value=True):
        r = client.get("/api/stocks/2330.TW/brokers?days=5&top=5")

    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "2330.TW"
    assert data["as_of"] == days[-1]
    top = data["top_brokers"]
    assert len(top) == 5
    assert [b["id"] for b in top] == ["C", "A", "D", "E", "F"]  # by net buy

    # Broker A: buys every day → consecutive 5
    a = next(b for b in top if b["id"] == "A")
    assert a["consecutive_buy_days"] == 5
    assert a["avg_buy_price"] == 50.0
    assert a["net_buy_volume"] == (100 - 20) * 5

    # Broker C: only bought today → consecutive 1
    c = next(b for b in top if b["id"] == "C")
    assert c["consecutive_buy_days"] == 1
    assert c["avg_buy_price"] == 51.0


def test_brokers_endpoint_empty_when_no_data():
    with patch("fetchers.broker.fetch_broker_daily", return_value=False):
        r = client.get("/api/stocks/2330.TW/brokers")
    assert r.status_code == 200
    body = r.json()
    assert body["top_brokers"] == []
    assert body["as_of"] is None


def test_fetch_broker_daily_skips_non_tw():
    assert fetch_broker_daily("AAPL") is False
