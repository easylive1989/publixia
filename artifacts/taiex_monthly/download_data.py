#!/usr/bin/env python3
"""Download public TAIEX source data. Uses a local cache and never executes JS."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import subprocess
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
ARCHIVE_URL = "https://www.011.idv.tw/Taiex/taiex-Native.js"
TWSE_URL = "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII"


def download(url: str) -> str:
    # curl uses the operating system certificate store on macOS.
    return subprocess.check_output(
        ["curl", "-sS", "-L", "--fail", "--max-time", "45",
         "-A", "Mozilla/5.0", url],
        text=True, encoding="utf-8-sig",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat,
                        default=datetime.now(ZoneInfo("Asia/Taipei")).date())
    parser.add_argument("--refresh", action="store_true",
                        help="Refresh the archive and all cached TWSE months.")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    archive = RAW / "archive_daily.js"
    if args.refresh or not archive.exists():
        archive.write_text(download(ARCHIVE_URL), encoding="utf-8")

    end = int(datetime.combine(args.as_of, datetime.max.time(),
                               tzinfo=ZoneInfo("Asia/Taipei")).timestamp())
    yahoo_url = f"{YAHOO_URL}?period1=0&period2={end}&interval=1d"
    yahoo = RAW / "yahoo_daily.json"
    if args.refresh or not yahoo.exists():
        raw = download(yahoo_url)
        if json.loads(raw)["chart"].get("error"):
            raise ValueError("Yahoo returned an error")
        yahoo.write_text(raw, encoding="utf-8")

    # Early official daily data includes Saturday sessions that some vendors omit.
    # Later daily OHLC comes from Yahoo; current-month TWSE data takes precedence.
    months = [(y, m) for y in range(1999, 2003) for m in range(1, 13)
              if (1999, 1) <= (y, m) <= min((2002, 9), (args.as_of.year, args.as_of.month))]
    current_month = (args.as_of.year, args.as_of.month)
    if current_month not in months:
        months.append(current_month)
    manifest = []
    for i, (year, month) in enumerate(months, 1):
        key = f"{year:04d}{month:02d}"
        path = RAW / f"twse_{key}.json"
        url = f"{TWSE_URL}?response=json&date={key}01"
        current = (year, month) == current_month
        if args.refresh or not path.exists():
            for attempt in range(4):
                try:
                    raw = download(url)
                    result = json.loads(raw)
                    if result.get("stat") != "OK" or not result.get("data"):
                        # On the first day of a month there may be no session yet.
                        if current and "沒有符合條件" in result.get("stat", ""):
                            break
                        raise ValueError(f"{key}: {result.get('stat')}")
                    path.write_text(raw, encoding="utf-8")
                    break
                except (ValueError, subprocess.SubprocessError):
                    if attempt == 3:
                        raise
                    time.sleep(2 ** (attempt + 1))
            time.sleep(1)
        if path.exists():
            manifest.append({"file": path.name, "url": url})
        if i % 12 == 0 or i == len(months):
            print(f"TWSE: {i}/{len(months)} months, through {key}", flush=True)
    (RAW / "manifest.json").write_text(json.dumps({
        "retrieved_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(),
        "as_of": args.as_of.isoformat(),
        "archive_url": ARCHIVE_URL,
        "yahoo_url": yahoo_url,
        "twse": manifest,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
