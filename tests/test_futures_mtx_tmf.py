"""Smoke tests for MTX/TMF fetchers + verify the strategy engine hook fires."""
from db.connection import get_connection
from fetchers import futures as mod
from repositories.futures import get_futures_daily_range


def _mock_finmind_response(symbol: str) -> list[dict]:
    """Two trading days, two contracts each — front-month is the higher-volume one."""
    return [
        {"date": "2026-04-01", "contract_date": "202604",
         "open": 17000, "max": 17100, "min": 16900, "close": 17050,
         "volume": 12345, "settlement_price": 17050,
         "open_interest": 100, "trading_session": "position"},
        {"date": "2026-04-02", "contract_date": "202604",
         "open": 17100, "max": 17200, "min": 17050, "close": 17180,
         "volume": 12000, "settlement_price": 17180,
         "open_interest": 110, "trading_session": "position"},
    ]


def test_fetch_mtx_writes_rows_under_mtx_symbol(monkeypatch):
    monkeypatch.setattr(
        mod, "_request",
        lambda symbol, start, end: _mock_finmind_response(symbol),
    )
    called = []
    monkeypatch.setattr(
        "services.strategy_engine.on_futures_data_written",
        lambda contract, date: called.append((contract, date)),
    )

    ok = mod.fetch_tw_futures_mtx()
    assert ok is True

    rows = get_futures_daily_range("MTX", "2026-04-01")
    assert {r["date"] for r in rows} == {"2026-04-01", "2026-04-02"}
    # No TX rows should have been written by the MTX fetcher.
    assert get_futures_daily_range("TX", "2026-04-01") == []

    assert called == [("MTX", "2026-04-02")]


def test_fetch_tmf_writes_rows_under_tmf_symbol(monkeypatch):
    monkeypatch.setattr(
        mod, "_request",
        lambda symbol, start, end: _mock_finmind_response(symbol),
    )
    called = []
    monkeypatch.setattr(
        "services.strategy_engine.on_futures_data_written",
        lambda contract, date: called.append((contract, date)),
    )

    assert mod.fetch_tw_futures_tmf() is True

    rows = get_futures_daily_range("TMF", "2026-04-01")
    assert len(rows) == 2
    assert called == [("TMF", "2026-04-02")]


def test_fetch_tw_still_works_and_calls_engine(monkeypatch):
    monkeypatch.setattr(
        mod, "_request",
        lambda symbol, start, end: _mock_finmind_response(symbol),
    )
    called = []
    monkeypatch.setattr(
        "services.strategy_engine.on_futures_data_written",
        lambda contract, date: called.append((contract, date)),
    )

    assert mod.fetch_tw_futures() is True

    assert {r["date"] for r in get_futures_daily_range("TX", "2026-04-01")} == {
        "2026-04-01", "2026-04-02",
    }
    # TX hook fires too — engine must see all three contracts.
    assert called == [("TX", "2026-04-02")]
