"""Verify the one-shot non-trading-day cleanup: keeps real trading days,
deletes weekend/holiday pollution, and stays fail-safe when yfinance
returns nothing for a ticker."""
from datetime import datetime
from unittest.mock import patch

import pandas as pd

import db


def _hist(dates: list[str]) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame({"Close": [1.0] * len(dates)}, index=idx)


def _seed_indicator(indicator: str, dates: list[str]):
    for d in dates:
        db.save_indicator(indicator, 100.0, timestamp=datetime.fromisoformat(f"{d}T13:30:00"))


def _seed_stock(ticker: str, dates: list[str]):
    db.add_watched_ticker(1, ticker)
    for d in dates:
        db.save_stock_snapshot(ticker, 100.0, 0.0, 0.0, "TWD", ticker, date=d)


def _dates_for(table: str, key_col: str, key_value: str) -> list[str]:
    rows = db.get_connection().execute(
        f"SELECT date FROM {table} WHERE {key_col}=? ORDER BY date",
        (key_value,),
    ).fetchall()
    return [r["date"] for r in rows]


def test_indicator_non_trading_days_removed():
    db.init_db()
    # Seed: 2 real trading days + 2 weekend rows + 1 holiday row.
    _seed_indicator("taiex", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03"])

    # yfinance reports only the real trading days.
    real_days = ["2026-04-29", "2026-04-30"]
    with patch("scripts.dedupe_non_trading_days.yf.Ticker") as MockTicker:
        MockTicker.return_value.history.return_value = _hist(real_days)
        from scripts.dedupe_non_trading_days import cleanup
        summary = cleanup(dry_run=False)

    remaining = _dates_for("indicator_snapshots", "indicator", "taiex")
    assert remaining == real_days
    assert summary["indicator:taiex"] == 3


def test_stock_non_trading_days_removed():
    db.init_db()
    _seed_stock("2330.TW", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02"])

    real_days = ["2026-04-29", "2026-04-30"]
    with patch("scripts.dedupe_non_trading_days.yf.Ticker") as MockTicker:
        MockTicker.return_value.history.return_value = _hist(real_days)
        from scripts.dedupe_non_trading_days import cleanup
        summary = cleanup(dry_run=False)

    remaining = _dates_for("stock_snapshots", "ticker", "2330.TW")
    assert remaining == real_days
    assert summary["stock:2330.TW"] == 2


def test_dry_run_does_not_modify_db():
    db.init_db()
    _seed_indicator("taiex", ["2026-04-29", "2026-05-01"])

    real_days = ["2026-04-29"]
    with patch("scripts.dedupe_non_trading_days.yf.Ticker") as MockTicker:
        MockTicker.return_value.history.return_value = _hist(real_days)
        from scripts.dedupe_non_trading_days import cleanup
        summary = cleanup(dry_run=True)

    # Both dates still present.
    assert _dates_for("indicator_snapshots", "indicator", "taiex") == ["2026-04-29", "2026-05-01"]
    # But the summary still reports the 1 row that would have been deleted.
    assert summary["indicator:taiex"] == 1


def test_empty_yfinance_response_keeps_rows():
    """Fail-safe: if yfinance returns no calendar for a ticker, don't wipe its rows."""
    db.init_db()
    _seed_stock("BOGUS", ["2026-04-29", "2026-05-01"])

    with patch("scripts.dedupe_non_trading_days.yf.Ticker") as MockTicker:
        MockTicker.return_value.history.return_value = pd.DataFrame()
        from scripts.dedupe_non_trading_days import cleanup
        summary = cleanup(dry_run=False)

    # All seeded dates kept — the script must not delete blindly.
    assert _dates_for("stock_snapshots", "ticker", "BOGUS") == ["2026-04-29", "2026-05-01"]
    assert summary["stock:BOGUS"] == 0
