"""Unit tests for services.strike_oi_view.build_strike_oi_block."""
from services.strike_oi_view import build_strike_oi_block


def _r(expiry, strike, put_call, oi):
    return {
        "date":          "2026-05-09",
        "expiry_month":  expiry,
        "strike":        strike,
        "put_call":      put_call,
        "open_interest": oi,
        "settle_price":  None,
    }


def test_empty_rows_return_empty_block():
    out = build_strike_oi_block([])
    assert out == {
        "date": None,
        "expiry_months": [],
        "near_month": None,
        "by_expiry": {},
    }


def test_groups_per_expiry_and_orders_strikes():
    rows = [
        _r("202506", 17500, "CALL", 100),
        _r("202506", 17000, "CALL", 300),
        _r("202506", 17000, "PUT",  500),
        _r("202507", 17500, "PUT",   80),
    ]
    out = build_strike_oi_block(rows)
    assert out["date"] == "2026-05-09"
    assert out["expiry_months"] == ["202506", "202507"]
    s06 = out["by_expiry"]["202506"]
    assert s06["strikes"] == [17000.0, 17500.0]
    assert s06["call_oi"] == [300, 100]
    assert s06["put_oi"]  == [500, 0]
    s07 = out["by_expiry"]["202507"]
    assert s07["strikes"] == [17500.0]
    assert s07["call_oi"] == [0]
    assert s07["put_oi"]  == [80]


def test_near_month_skips_weekly_contracts():
    rows = [
        _r("202506W2", 17000, "CALL", 100),
        _r("202506",   17000, "CALL", 200),
        _r("202507",   17000, "CALL", 300),
    ]
    out = build_strike_oi_block(rows)
    # All three appear in expiry_months, but near_month is the earliest
    # monthly (non-weekly) one.
    assert "202506W2" in out["expiry_months"]
    assert out["near_month"] == "202506"


def test_near_month_falls_back_to_none_when_only_weeklies():
    rows = [
        _r("202506W2", 17000, "CALL", 100),
    ]
    out = build_strike_oi_block(rows)
    assert out["near_month"] is None
