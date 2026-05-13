"""End-to-end tests for /api/futures/tw/foreign-flow.

Conftest overrides require_token / require_user, so permission-gating
tests must explicitly construct a fresh app or mutate the seeded user
row to flip can_view_foreign_futures on/off.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from api.routes import foreign_futures as foreign_futures_route
from db.connection import get_connection
from repositories.users import set_foreign_futures_permission
from repositories.futures import save_futures_daily_rows
from repositories.institutional_futures import (
    save_institutional_futures_rows, save_settlement_dates,
)
from repositories.institutional_options import save_institutional_options_rows
from repositories.txo_strike_oi import save_txo_strike_oi_rows
from repositories.large_trader import save_large_trader_rows
from repositories.indicators import save_indicator


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


def test_403_when_user_lacks_permission():
    # Seeded user defaults to can_view_foreign_futures = 0
    r = client.get("/api/futures/tw/foreign-flow?time_range=6M")
    assert r.status_code == 403
    assert r.json()["detail"] == "no foreign futures permission"


def test_400_on_unknown_time_range():
    _grant()
    r = client.get("/api/futures/tw/foreign-flow?time_range=2W")
    assert r.status_code == 400


def test_200_response_shape():
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
        "retail_ratio", "foreign_spot_net",
        "settlement_dates",
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
    # oi_by_strike block always present (empty shape when no rows).
    assert "oi_by_strike" in opt
    assert set(opt["oi_by_strike"].keys()) == {
        "date", "expiry_months", "near_month", "by_expiry",
    }
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
    # foreign_spot_net aligns with dates; no indicator rows seeded → all None
    assert body["foreign_spot_net"] == [None, None]
    # Settlement date inside window
    assert "2025-05-21" in body["settlement_dates"]


def test_foreign_spot_net_projected_onto_kline_timeline():
    from datetime import datetime
    _grant()
    _seed_minimum()
    save_indicator(
        "total_foreign_net", 12.34,
        timestamp=datetime(2025, 5, 1), date="2025-05-01",
    )
    save_indicator(
        "total_foreign_net", -5.67,
        timestamp=datetime(2025, 5, 2), date="2025-05-02",
    )
    r = client.get("/api/futures/tw/foreign-flow?time_range=3Y")
    assert r.status_code == 200
    body = r.json()
    assert body["foreign_spot_net"] == [12.34, -5.67]
    assert len(body["foreign_spot_net"]) == len(body["dates"])


def test_404_when_no_tx_history():
    _grant()
    # No futures_daily rows seeded.
    r = client.get("/api/futures/tw/foreign-flow?time_range=6M")
    assert r.status_code == 404


def test_options_block_projected_onto_kline_timeline():
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


def test_strike_oi_block_uses_latest_available_date():
    _grant()
    _seed_minimum()
    # Seed two trading days of strike OI; the route should surface only
    # the latest one in the oi_by_strike block.
    save_txo_strike_oi_rows([
        {"symbol": "TXO", "date": "2025-05-01", "expiry_month": "202505",
         "strike": 17000.0, "put_call": "CALL", "open_interest": 100,
         "settle_price": None},
        {"symbol": "TXO", "date": "2025-05-02", "expiry_month": "202505",
         "strike": 17000.0, "put_call": "CALL", "open_interest": 400,
         "settle_price": None},
        {"symbol": "TXO", "date": "2025-05-02", "expiry_month": "202505",
         "strike": 17000.0, "put_call": "PUT",  "open_interest": 700,
         "settle_price": None},
        {"symbol": "TXO", "date": "2025-05-02", "expiry_month": "202505W2",
         "strike": 17000.0, "put_call": "CALL", "open_interest": 50,
         "settle_price": None},
    ])
    r = client.get("/api/futures/tw/foreign-flow?time_range=3Y")
    assert r.status_code == 200
    block = r.json()["options"]["oi_by_strike"]
    assert block["date"] == "2025-05-02"
    # near_month picks the monthly contract, not the weekly.
    assert block["near_month"] == "202505"
    assert set(block["expiry_months"]) == {"202505", "202505W2"}
    monthly = block["by_expiry"]["202505"]
    assert monthly["strikes"] == [17000.0]
    assert monthly["call_oi"] == [400]
    assert monthly["put_oi"]  == [700]


def _stub_refresh_fetchers(behaviour: dict[str, Exception | None] | None = None):
    """Patch the 5 fetchers wired into the refresh endpoint.

    behaviour maps fetcher name → None (succeed) or an Exception
    (raised when invoked). Returns the list of names actually called,
    in order, plus the mock objects so tests can assert call counts.
    """
    behaviour = behaviour or {}
    calls: list[str] = []

    def _make(name: str):
        def _fn():
            calls.append(name)
            err = behaviour.get(name)
            if err is not None:
                raise err
        return _fn

    patched = [
        (name, _make(name)) for name, _ in foreign_futures_route._REFRESH_FETCHERS
    ]
    return calls, patched


def test_refresh_runs_all_fetchers_and_reports_ok():
    _grant()
    calls, patched = _stub_refresh_fetchers()
    with patch.object(foreign_futures_route, "_REFRESH_FETCHERS", patched):
        r = client.post("/api/futures/tw/foreign-flow/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert calls == [
        "tw_futures", "inst_futures", "inst_options",
        "large_trader", "txo_strike_oi",
    ]
    for name in calls:
        assert body["results"][name] == {"status": "ok", "detail": None}


def test_refresh_continues_after_individual_fetcher_failure():
    _grant()
    calls, patched = _stub_refresh_fetchers(
        behaviour={"inst_options": RuntimeError("TAIFEX down")},
    )
    with patch.object(foreign_futures_route, "_REFRESH_FETCHERS", patched):
        r = client.post("/api/futures/tw/foreign-flow/refresh")
    assert r.status_code == 200
    body = r.json()
    # Partial failure → ok=False but the remaining fetchers still ran.
    assert body["ok"] is False
    assert calls == [
        "tw_futures", "inst_futures", "inst_options",
        "large_trader", "txo_strike_oi",
    ]
    assert body["results"]["inst_options"]["status"] == "error"
    assert "TAIFEX down" in body["results"]["inst_options"]["detail"]
    assert body["results"]["tw_futures"]["status"] == "ok"
    assert body["results"]["large_trader"]["status"] == "ok"


def test_refresh_returns_409_when_already_running():
    _grant()
    # Pretend another request is mid-flight by holding the lock.
    assert foreign_futures_route._refresh_lock.acquire(blocking=False)
    try:
        r = client.post("/api/futures/tw/foreign-flow/refresh")
    finally:
        foreign_futures_route._refresh_lock.release()
    assert r.status_code == 409
    assert "already in progress" in r.json()["detail"].lower()


def test_refresh_blocked_without_permission():
    # Seeded user defaults to can_view_foreign_futures = 0 → 403 before
    # any fetcher runs.
    calls, patched = _stub_refresh_fetchers()
    with patch.object(foreign_futures_route, "_REFRESH_FETCHERS", patched):
        r = client.post("/api/futures/tw/foreign-flow/refresh")
    assert r.status_code == 403
    assert calls == []
