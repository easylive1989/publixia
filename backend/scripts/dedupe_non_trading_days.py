"""One-shot cleanup: remove indicator/stock snapshots that fall on non-trading days.

After 0005_snapshot_date_dedupe.sql collapsed multiple intraday rows into one
per (key, date), some surviving rows are pollution from the old 15-minute
scheduler running on weekends/holidays (yfinance returned the previous close).

This script asks yfinance for each ticker's actual trading-day calendar and
deletes any row whose date is NOT a real trading day. Market-agnostic
indicators (fear_greed, ndc, chip_total children, tw_volume, us_volume) are
left alone — they were already daily-scheduled and don't have intraday
pollution.

Usage:
    python -m scripts.dedupe_non_trading_days [--dry-run]

Fail-safe: if yfinance returns nothing for a ticker (network failure, delisted),
its rows are kept rather than wiped.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yfinance as yf

from db.connection import get_connection

INDICATOR_TICKERS: dict[str, str] = {
    "taiex": "^TWII",
    "fx": "TWD=X",
}

HISTORY_PERIOD = "5y"


def trading_days(ticker: str) -> set[str]:
    hist = yf.Ticker(ticker).history(period=HISTORY_PERIOD)
    if hist.empty:
        return set()
    return {idx.strftime("%Y-%m-%d") for idx in hist.index}


def find_non_trading_rows(
    conn, table: str, key_col: str, key_value: str, days: set[str]
) -> list[int]:
    rows = conn.execute(
        f"SELECT id, date FROM {table} WHERE {key_col}=?",
        (key_value,),
    ).fetchall()
    return [r["id"] for r in rows if r["date"] not in days]


def delete_rows(conn, table: str, ids: list[int]) -> None:
    if not ids:
        return
    conn.executemany(f"DELETE FROM {table} WHERE id=?", [(i,) for i in ids])


def cleanup(dry_run: bool = False) -> dict:
    """Delete non-trading-day rows; returns per-key counts."""
    summary: dict[str, int] = {}
    with get_connection() as conn:
        for indicator, ticker in INDICATOR_TICKERS.items():
            days = trading_days(ticker)
            if not days:
                print(f"[skip] indicator={indicator}: no calendar from {ticker}")
                summary[f"indicator:{indicator}"] = 0
                continue
            ids = find_non_trading_rows(
                conn, "indicator_snapshots", "indicator", indicator, days
            )
            if not dry_run:
                delete_rows(conn, "indicator_snapshots", ids)
            summary[f"indicator:{indicator}"] = len(ids)
            print(
                f"[indicator] {indicator}: {'would delete' if dry_run else 'deleted'} "
                f"{len(ids)} non-trading-day rows"
            )

        tickers = [
            r["ticker"]
            for r in conn.execute(
                "SELECT DISTINCT ticker FROM stock_snapshots"
            ).fetchall()
        ]
        for t in tickers:
            days = trading_days(t)
            if not days:
                print(f"[skip] stock={t}: no calendar from yfinance")
                summary[f"stock:{t}"] = 0
                continue
            ids = find_non_trading_rows(conn, "stock_snapshots", "ticker", t, days)
            if not dry_run:
                delete_rows(conn, "stock_snapshots", ids)
            summary[f"stock:{t}"] = len(ids)
            print(
                f"[stock] {t}: {'would delete' if dry_run else 'deleted'} "
                f"{len(ids)} non-trading-day rows"
            )

    total = sum(summary.values())
    print(f"\n{'Would delete' if dry_run else 'Deleted'} {total} rows total")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be deleted without modifying the DB",
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
