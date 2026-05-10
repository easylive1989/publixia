"""End-to-end tests for /api/futures/tw/foreign-flow.

Conftest overrides require_token / require_user, so permission-gating
tests must explicitly construct a fresh app or mutate the seeded user
row to flip can_view_foreign_futures on/off.
"""
from fastapi.testclient import TestClient

from main import app
from db.connection import get_connection
from repositories.users import set_foreign_futures_permission
from repositories.futures import save_futures_daily_rows
from repositories.institutional_futures import (
    save_institutional_futures_rows, save_settlement_dates,
)
from repositories.institutional_options import save_institutional_options_rows
from repositories.large_trader import save_large_trader_rows


client = TestClient(app)


def _grant():
    set_foreign_futures_permission(1, True)


def _seed_minimum():
    """Seed enough rows for the route to return a 200 with data."""
    save_futures_daily_rows([
        {"symbol": "TX", "date": "2025-05-01", "contract_date": "202505",
         "open": 17000, "high": 17100, "low": 16900, "close": 17000,
         "volume": 1, "open_interest": 1, "settlement": 17000},
        {"symbol": "TX", "date": "2025-05-02", "contract_date": "202505",
         "open": 17000, "high": 17200, "low": 16950, "close": 17150,
         "volume": 1, "open_interest": 1, "settlement": 17150},
    ])
    save_institutional_futures_rows([
        {"symbol": "TX", "date": "2025-05-01",
         "foreign_long_oi": 100, "foreign_short_oi": 0,
         "foreign_long_amount": 320_000.0, "foreign_short_amount": 0.0},
        {"symbol": "TX", "date": "2025-05-02",
         "foreign_long_oi": 130, "foreign_short_oi": 0,
         "foreign_long_amount": 419_500.0, "foreign_short_amount": 0.0},
    ])
    save_settlement_dates("TX", [
        {"year_month": "2025-05", "settlement_date": "2025-05-21"},
    ])
    save_large_trader_rows([
        {"date": "2025-05-01", "market_oi": 100_000,
         "top5_long_oi": 0, "top5_short_oi": 0,
         "top10_long_oi": 60_000, "top10_short_oi": 70_000},
        {"date": "2025-05-02", "market_oi": 100_000,
         "top5_long_oi": 0, "top5_short_oi": 0,
         "top10_long_oi": 65_000, "top10_short_oi": 60_000},
    ])


def _bypass_lazy_fetch(monkeypatch):
    """The route's best-effort lazy-fetch hits the network; stub it out."""
    import api.routes.foreign_futures as route_mod
    monkeypatch.setattr(route_mod, "fetch_tw_futures",            lambda: True)
    monkeypatch.setattr(route_mod, "fetch_tw_futures_mtx",        lambda: True)
    monkeypatch.setattr(route_mod, "fetch_inst_latest",           lambda: True)
    monkeypatch.setattr(route_mod, "fetch_options_latest",        lambda: True)
    monkeypatch.setattr(route_mod, "fetch_large_trader_latest",   lambda: True)


def test_403_when_user_lacks_permission(monkeypatch):
    _bypass_lazy_fetch(monkeypatch)
    # Seeded user defaults to can_view_foreign_futures = 0
    r = client.get("/api/futures/tw/foreign-flow?time_range=6M")
    assert r.status_code == 403
    assert r.json()["detail"] == "no foreign futures permission"


def test_400_on_unknown_time_range(monkeypatch):
    _bypass_lazy_fetch(monkeypatch)
    _grant()
    r = client.get("/api/futures/tw/foreign-flow?time_range=2W")
    assert r.status_code == 400


def test_200_response_shape(monkeypatch):
    _bypass_lazy_fetch(monkeypatch)
    _grant()
    _seed_minimum()
    # Pin "today" in the route by giving everything dates that fall
    # inside its 6M lookback window — May 2025 rows are well within
    # 6 months of today (2026-05-10) for the test conftest.
    r = client.get("/api/futures/tw/foreign-flow?time_range=3Y")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "symbol", "name", "currency", "time_range",
        "dates", "candles",
        "cost", "net_position", "net_change",
        "unrealized_pnl", "realized_pnl",
        "retail_ratio", "settlement_dates",
        "options",
    ):
        assert key in body, f"missing key {key}"
    # options block always present (empty arrays/dict if no rows).
    opt = body["options"]
    for k in (
        "foreign_call_long_amount", "foreign_call_short_amount",
        "foreign_put_long_amount",  "foreign_put_short_amount",
        "detail_by_date",
    ):
        assert k in opt, f"missing options key {k}"
    # All chart series align with dates length.
    assert len(opt["foreign_call_long_amount"]) == len(body["dates"])
    assert body["symbol"] == "TX"
    assert body["time_range"] == "3Y"
    # Two seeded TX bars → two-element aligned arrays.
    assert len(body["dates"]) == 2
    assert len(body["candles"]) == 2
    assert len(body["cost"])    == 2
    assert len(body["net_position"]) == 2
    assert len(body["retail_ratio"]) == 2
    # Cost on day 1 = 320_000_000 / (100 × 200) = 16_000
    assert body["cost"][0] == 16_000
    # retail_ratio[0]: (70_000 - 60_000) / 100_000 × 100 = +10.0
    # retail_ratio[1]: (60_000 - 65_000) / 100_000 × 100 = -5.0
    assert body["retail_ratio"][0] == 10.0
    assert body["retail_ratio"][1] == -5.0
    # Settlement date inside window
    assert "2025-05-21" in body["settlement_dates"]


def test_404_when_no_tx_history(monkeypatch):
    _bypass_lazy_fetch(monkeypatch)
    _grant()
    # No futures_daily rows seeded.
    r = client.get("/api/futures/tw/foreign-flow?time_range=6M")
    assert r.status_code == 404


def test_options_block_projected_onto_kline_timeline(monkeypatch):
    _bypass_lazy_fetch(monkeypatch)
    _grant()
    _seed_minimum()
    # Seed TXO options rows for one of the two K-line dates only —
    # the other date should land as None in the aligned chart series.
    save_institutional_options_rows([
        {"symbol": "TXO", "date": "2025-05-02",
         "identity": "foreign", "put_call": "CALL",
         "long_oi": 13_000, "short_oi": 12_000,
         "long_amount": 2_400_000.0, "short_amount": 2_200_000.0},
        {"symbol": "TXO", "date": "2025-05-02",
         "identity": "foreign", "put_call": "PUT",
         "long_oi": 18_000, "short_oi": 15_000,
         "long_amount":   180_000.0, "short_amount":   160_000.0},
        {"symbol": "TXO", "date": "2025-05-02",
         "identity": "investment_trust", "put_call": "CALL",
         "long_oi": 10, "short_oi": 5,
         "long_amount": 1_000.0, "short_amount": 500.0},
        {"symbol": "TXO", "date": "2025-05-02",
         "identity": "dealer", "put_call": "PUT",
         "long_oi": 20_000, "short_oi": 18_000,
         "long_amount": 200_000.0, "short_amount": 190_000.0},
    ])
    r = client.get("/api/futures/tw/foreign-flow?time_range=3Y")
    assert r.status_code == 200
    body = r.json()
    opt = body["options"]
    # Two K-line dates → arrays of length 2; first day is None (no rows).
    assert opt["foreign_call_long_amount"]  == [None, 2_400_000.0]
    assert opt["foreign_call_short_amount"] == [None, 2_200_000.0]
    assert opt["foreign_put_long_amount"]   == [None,   180_000.0]
    assert opt["foreign_put_short_amount"]  == [None,   160_000.0]
    # detail_by_date only contains dates with rows; identity coverage
    # is whatever was seeded for that date.
    assert "2025-05-01" not in opt["detail_by_date"]
    rows_2 = opt["detail_by_date"]["2025-05-02"]
    assert len(rows_2) == 4
    by_key = {(r["identity"], r["put_call"]): r for r in rows_2}
    assert by_key[("foreign", "CALL")]["long_oi"]      == 13_000
    assert by_key[("foreign", "PUT")]["short_amount"]  == 160_000.0
    assert by_key[("dealer",  "PUT")]["short_oi"]      == 18_000
    assert by_key[("investment_trust", "CALL")]["long_amount"] == 1_000.0
