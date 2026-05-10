"""One-shot backfill for the foreign-investor futures-flow page.

Pulls 5 years of TX/MTX foreign-investor positions from TAIFEX and 5
years of TX settlement dates. Run after the migrations land but before
exposing the page to users:

    python -m scripts.backfill_inst_futures            # default 5y
    python -m scripts.backfill_inst_futures --years 1  # smaller window

Idempotent — both writers are upserts.
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import init_db                            # noqa: E402
from fetchers.institutional_futures import backfill as backfill_inst    # noqa: E402
from fetchers.futures_settlement import fetch_settlement_dates           # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5,
                        help="how many years to backfill (default: 5)")
    parser.add_argument("--start", type=str, default=None,
                        help="explicit start date (YYYY-MM-DD); overrides --years")
    args = parser.parse_args()

    init_db()  # ensure migrations applied

    today = datetime.now(timezone.utc).astimezone().date()
    if args.start:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d").date()
    else:
        start_dt = today - timedelta(days=365 * args.years)

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str   = today.strftime("%Y-%m-%d")

    print(f"[backfill] institutional_futures {start_str} → {end_str} …")
    n_inst = backfill_inst(start_str, end_str)
    print(f"[backfill] inst rows saved: {n_inst}")

    print(f"[backfill] settlement dates {start_str} → +12mo …")
    n_settle = fetch_settlement_dates(start_date=start_str)
    print(f"[backfill] settlement months saved: {n_settle}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
