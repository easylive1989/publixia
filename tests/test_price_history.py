"""7d/1m price-window computation (network stubbed)."""
from datetime import date, datetime, timezone

import pytest

import services.price_history as ph

POST = datetime(2026, 5, 1, 3, 0, 0, tzinfo=timezone.utc)
CLOSES = {
    date(2026, 4, 30): 99.0,
    date(2026, 5, 1): 100.0,   # base (post day)
    date(2026, 5, 4): 102.0,
    date(2026, 5, 7): 105.0,
    date(2026, 5, 8): 107.0,   # post + 7
    date(2026, 5, 15): 120.0,
    date(2026, 5, 22): 125.0,
    date(2026, 5, 29): 130.0,  # last trading day <= post + 30 (05-31)
}


@pytest.fixture(autouse=True)
def _stub_closes(monkeypatch):
    # respect the requested [start, end] range so "latest" reflects ``today``
    monkeypatch.setattr(
        ph, "_closes_for",
        lambda t, m, start, end: {d: p for d, p in CLOSES.items() if start <= d <= end},
    )


def test_full_window_done():
    w = ph.compute_window("2330", "TW", POST, today=date(2026, 6, 5))
    assert w["status"] == "done"
    assert w["base_price"] == 100.0 and w["base_date"] == "2026-05-01"
    assert round(w["pct_7d"], 4) == 0.07     # 107 vs 100
    assert round(w["pct_1m"], 4) == 0.30     # 130 vs 100
    assert round(w["pct_latest"], 4) == 0.30  # latest close (05-29) vs 100


def test_partial_only_7d_elapsed():
    w = ph.compute_window("2330", "TW", POST, today=date(2026, 5, 10))
    assert w["status"] == "partial"
    assert round(w["pct_7d"], 4) == 0.07
    assert w["pct_1m"] is None
    assert round(w["pct_latest"], 4) == 0.07  # latest available ≤ today (05-08)


def test_pending_nothing_elapsed():
    w = ph.compute_window("2330", "TW", POST, today=date(2026, 5, 2))
    assert w["status"] == "pending"
    assert w["base_price"] == 100.0
    assert w["pct_7d"] is None and w["pct_1m"] is None
    assert w["pct_latest"] == 0.0  # only the base close is available yet


def test_index_uses_twii_symbol():
    assert ph._yf_symbols("TAIEX", "INDEX") == ["^TWII"]


def test_unavailable_when_no_prices(monkeypatch):
    monkeypatch.setattr(ph, "_closes_for", lambda *a, **k: {})
    w = ph.compute_window("9999", "TW", POST, today=date(2026, 6, 5))
    assert w["status"] == "unavailable"
    assert w["base_price"] is None


def test_yf_symbols():
    assert ph._yf_symbols("2330", "TW") == ["2330.TW", "2330.TWO"]
    assert ph._yf_symbols("NVDA", "US") == ["NVDA"]
