"""Round-trip tests for the institutional_options repository."""
from repositories.institutional_options import (
    save_institutional_options_rows,
    get_institutional_options_range,
    get_latest_institutional_options_date,
)


def _row(date: str, *,
         symbol: str = "TXO", identity: str = "foreign",
         put_call: str = "CALL", **overrides) -> dict:
    base = {
        "symbol": symbol, "date": date,
        "identity": identity, "put_call": put_call,
        "long_oi":      10_000,
        "short_oi":     30_000,
        "long_amount":  500_000.0,    # 千元
        "short_amount": 1_500_000.0,
    }
    base.update(overrides)
    return base


def test_save_and_read_back_in_range():
    save_institutional_options_rows([
        _row("2026-04-01", identity="foreign", put_call="CALL"),
        _row("2026-04-01", identity="foreign", put_call="PUT",
             long_oi=5_000, short_oi=15_000),
        _row("2026-04-02", identity="dealer",  put_call="CALL",
             long_oi=8_000),
    ])

    rows = get_institutional_options_range("TXO", "2026-04-01")
    # 3 rows total; ordered by (date, identity, put_call) ascending.
    assert [(r["date"], r["identity"], r["put_call"]) for r in rows] == [
        ("2026-04-01", "foreign", "CALL"),
        ("2026-04-01", "foreign", "PUT"),
        ("2026-04-02", "dealer",  "CALL"),
    ]
    assert rows[0]["long_oi"]  == 10_000
    assert rows[1]["short_oi"] == 15_000


def test_upsert_overwrites_existing_row():
    save_institutional_options_rows([
        _row("2026-04-10", identity="foreign", put_call="CALL", long_oi=1),
    ])
    save_institutional_options_rows([
        _row("2026-04-10", identity="foreign", put_call="CALL", long_oi=2),
    ])
    rows = get_institutional_options_range("TXO", "2026-04-10")
    assert len(rows) == 1
    assert rows[0]["long_oi"] == 2


def test_distinct_put_call_keep_separate_rows_same_date():
    save_institutional_options_rows([
        _row("2026-04-15", identity="foreign", put_call="CALL", long_oi=11),
        _row("2026-04-15", identity="foreign", put_call="PUT",  long_oi=22),
    ])
    rows = get_institutional_options_range("TXO", "2026-04-15")
    by_pc = {r["put_call"]: r for r in rows}
    assert by_pc["CALL"]["long_oi"] == 11
    assert by_pc["PUT"]["long_oi"]  == 22


def test_get_latest_date_per_symbol():
    save_institutional_options_rows([
        _row("2026-04-20"),
        _row("2026-04-22"),
        _row("2026-04-21", symbol="TXO", identity="dealer", put_call="PUT"),
    ])
    assert get_latest_institutional_options_date("TXO") == "2026-04-22"
    assert get_latest_institutional_options_date("XYZ") is None


def test_range_filter_excludes_earlier_dates():
    save_institutional_options_rows([
        _row("2026-03-01"),
        _row("2026-03-15"),
        _row("2026-04-01"),
    ])
    rows = get_institutional_options_range("TXO", "2026-03-15")
    assert [r["date"] for r in rows] == ["2026-03-15", "2026-04-01"]
