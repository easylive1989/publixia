"""Repository tests for repositories.txo_strike_oi."""
from repositories.txo_strike_oi import (
    save_txo_strike_oi_rows,
    get_txo_strike_oi_on_date,
    get_txo_strike_oi_dates,
    get_latest_txo_strike_oi_date,
)


def _row(date, expiry, strike, put_call, oi, settle=None):
    return {
        "symbol":        "TXO",
        "date":          date,
        "expiry_month":  expiry,
        "strike":        strike,
        "put_call":      put_call,
        "open_interest": oi,
        "settle_price":  settle,
    }


def test_save_and_read_round_trip():
    save_txo_strike_oi_rows([
        _row("2026-05-09", "202506", 17000.0, "CALL", 3500, 86.0),
        _row("2026-05-09", "202506", 17000.0, "PUT",  4200, 73.0),
        _row("2026-05-09", "202506", 17500.0, "CALL", 1800, 43.0),
    ])
    rows = get_txo_strike_oi_on_date("TXO", "2026-05-09")
    assert len(rows) == 3
    keys = {(r["strike"], r["put_call"]) for r in rows}
    assert keys == {(17000.0, "CALL"), (17000.0, "PUT"), (17500.0, "CALL")}


def test_upsert_replaces_oi_on_conflict():
    save_txo_strike_oi_rows([
        _row("2026-05-09", "202506", 17000.0, "CALL", 3500),
    ])
    save_txo_strike_oi_rows([
        _row("2026-05-09", "202506", 17000.0, "CALL", 9999),
    ])
    rows = get_txo_strike_oi_on_date("TXO", "2026-05-09")
    assert len(rows) == 1
    assert rows[0]["open_interest"] == 9999


def test_distinct_dates_and_latest():
    save_txo_strike_oi_rows([
        _row("2026-05-07", "202506", 17000.0, "CALL", 100),
        _row("2026-05-08", "202506", 17000.0, "CALL", 100),
        _row("2026-05-09", "202506", 17000.0, "CALL", 100),
    ])
    dates = get_txo_strike_oi_dates("TXO", "2026-05-08")
    assert dates == ["2026-05-08", "2026-05-09"]
    assert get_latest_txo_strike_oi_date("TXO") == "2026-05-09"


def test_settle_price_nullable():
    save_txo_strike_oi_rows([
        _row("2026-05-09", "202506", 17000.0, "CALL", 3500, None),
    ])
    rows = get_txo_strike_oi_on_date("TXO", "2026-05-09")
    assert rows[0]["settle_price"] is None
