"""One-shot backfill for the group-volume heatmap.

Pulls the last ~35 calendar days of per-stock prices from FinMind, rolls
them up per industry, and writes one row per (trade_date, industry).
Must be run **before** users hit the heatmap card, because the rolling
20-day mean needs at least 20 prior days of history to surface a pct.

    python -m scripts.backfill_group_volume               # default 35 days
    python -m scripts.backfill_group_volume --days 60     # wider window

Idempotent — writer upserts on (trade_date, group_type, group_code).
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import init_db                                          # noqa: E402
from fetchers.group_volume import fetch_industry_volume_range   # noqa: E402
from repositories.group_volume import save_group_volume_batch   # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--days", type=int, default=35,
        help="how many calendar days to look back (default: 35 ≈ 25 trading days)",
    )
    parser.add_argument(
        "--start", type=str, default=None,
        help="explicit start date (YYYY-MM-DD); overrides --days",
    )
    args = parser.parse_args()

    init_db()

    today = datetime.now(timezone.utc).astimezone().date()
    if args.start:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d").date()
    else:
        start_dt = today - timedelta(days=args.days)

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str   = today.strftime("%Y-%m-%d")
    print(f"[backfill] group_volume industry {start_str} → {end_str} …")

    by_date = fetch_industry_volume_range(start_str, end_str)
    if not by_date:
        print("[backfill] FinMind returned no rows; nothing to write.")
        return 0

    total = 0
    # Chronological order is mandatory — mean_20d_value accumulates from
    # rows already in the table when each day's batch is written.
    for trade_date in sorted(by_date):
        n = save_group_volume_batch(trade_date, "industry", by_date[trade_date])
        total += n
        print(f"[backfill] {trade_date}: {n} industries")

    print(f"[backfill] done. Rows written: {total} across {len(by_date)} days.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
