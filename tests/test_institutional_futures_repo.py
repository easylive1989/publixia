"""Round-trip tests for the institutional_futures repository."""
from repositories.institutional_futures import (
    save_institutional_futures_rows,
    get_institutional_futures_range,
    get_latest_institutional_futures_date,
)


def _row(date: str, symbol: str = "TX", **overrides) -> dict:
    base = {
        "symbol": symbol, "date": date,
        "foreign_long_oi":      10_000,
        "foreign_short_oi":     30_000,
        "foreign_long_amount":  500_000.0,    # 千元
        "foreign_short_amount": 1_500_000.0,
    }
    base.update(overrides)
    return base


def test_save_and_read_back_in_range():
    save_institutional_futures_rows([
        _row("2025-05-01"),
        _row("2025-05-02"),
        _row("2025-05-03", symbol="MTX",
             foreign_long_oi=4_000, foreign_short_oi=12_000,
             foreign_long_amount=200_000, foreign_short_amount=600_000),
    ])

    tx = get_institutional_futures_range("TX",  "2025-05-01")
    mtx = get_institutional_futures_range("MTX", "2025-05-01")
    assert [r["date"] for r in tx]  == ["2025-05-01", "2025-05-02"]
    assert [r["date"] for r in mtx] == ["2025-05-03"]
    assert tx[0]["foreign_long_oi"] == 10_000
    assert mtx[0]["foreign_long_amount"] == 200_000.0


def test_upsert_overwrites_existing_row():
    save_institutional_futures_rows([_row("2025-06-01", foreign_long_oi=1)])
    save_institutional_futures_rows([_row("2025-06-01", foreign_long_oi=2)])
    rows = get_institutional_futures_range("TX", "2025-06-01")
    assert len(rows) == 1
    assert rows[0]["foreign_long_oi"] == 2


def test_get_latest_date_per_symbol():
    save_institutional_futures_rows([
        _row("2025-07-01", symbol="TX"),
        _row("2025-07-03", symbol="TX"),
        _row("2025-07-02", symbol="MTX",
             foreign_long_oi=0, foreign_short_oi=0,
             foreign_long_amount=0, foreign_short_amount=0),
    ])
    assert get_latest_institutional_futures_date("TX")  == "2025-07-03"
    assert get_latest_institutional_futures_date("MTX") == "2025-07-02"
    assert get_latest_institutional_futures_date("TMF") is None
