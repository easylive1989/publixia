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


def _bypass_lazy_fetch(monkeypatch):
    """The route's best-effort lazy-fetch hits the network; stub it out."""
    import api.routes.foreign_futures as route_mod
    monkeypatch.setattr(route_mod, "fetch_tw_futures",     lambda: True)
    monkeypatch.setattr(route_mod, "fetch_tw_futures_mtx", lambda: True)
    monkeypatch.setattr(route_mod, "fetch_inst_latest",    lambda: True)


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
        "settlement_dates",
    ):
        assert key in body, f"missing key {key}"
    assert body["symbol"] == "TX"
    assert body["time_range"] == "3Y"
    # Two seeded TX bars → two-element aligned arrays.
    assert len(body["dates"]) == 2
    assert len(body["candles"]) == 2
    assert len(body["cost"])    == 2
    assert len(body["net_position"]) == 2
    # Cost on day 1 = 320_000_000 / (100 × 200) = 16_000
    assert body["cost"][0] == 16_000
    # Settlement date inside window
    assert "2025-05-21" in body["settlement_dates"]


def test_404_when_no_tx_history(monkeypatch):
    _bypass_lazy_fetch(monkeypatch)
    _grant()
    # No futures_daily rows seeded.
    r = client.get("/api/futures/tw/foreign-flow?time_range=6M")
    assert r.status_code == 404
