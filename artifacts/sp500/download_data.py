#!/usr/bin/env python3
"""下載標普 500 (^GSPC) 日資料快照；排除尚未收盤的交易日。"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
NY = ZoneInfo("America/New_York")
URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, help="紐約日期，YYYY-MM-DD")
    parser.add_argument("--refresh", action="store_true", help="重新下载，而非重用現有快照")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    raw_path, manifest_path = RAW / "yahoo_daily.json", RAW / "manifest.json"
    if raw_path.exists() and manifest_path.exists() and not args.refresh:
        cached = json.loads(manifest_path.read_text())
        if args.as_of is None or str(args.as_of) == cached["requested_as_of"]:
            print(f"使用現有快照（截至 {cached['as_of']}）；更新請加 --refresh")
            return
    now = datetime.now(timezone.utc)
    target = args.as_of or now.astimezone(NY).date()
    if target > now.astimezone(NY).date() or target < date(1927, 12, 30):
        parser.error("截止日期需介於 1927-12-30 和紐約今日之間")
    end = min(int(now.timestamp()), int(datetime.combine(target + timedelta(days=1), time.min, NY).timestamp()))
    # A negative Unix timestamp is necessary: period1=0 loses pre-1970 history.
    url = f"{URL}?period1=-2208988800&period2={end}&interval=1d"
    raw = subprocess.check_output(["curl", "-sS", "-L", "--fail", "--max-time", "60",
                                   "-A", "Mozilla/5.0", url], text=True, encoding="utf-8")
    payload = json.loads(raw)["chart"]
    if payload.get("error") or not payload.get("result"):
        raise ValueError(f"Yahoo response error: {payload.get('error')}")
    result = payload["result"][0]
    if result["meta"]["symbol"] != "^GSPC" or not result.get("timestamp"):
        raise ValueError("Wrong symbol or empty data")
    regular = result["meta"].get("currentTradingPeriod", {}).get("regular")
    cutoff = target
    if regular is not None and now.timestamp() < regular["end"]:
        cutoff = min(cutoff, datetime.fromtimestamp(regular["start"], NY).date() - timedelta(days=1))
    elif regular is None and target == now.astimezone(NY).date():
        # Without session metadata, conservatively exclude today's observation.
        cutoff = target - timedelta(days=1)
    manifest = {
        "retrieved_at": now.isoformat(), "requested_as_of": str(target), "as_of": str(cutoff),
        "exchange_timezone": "America/New_York", "symbol": "^GSPC", "url": url,
        "index_launch_date": "1957-03-04", "official_first_value_date": "1928-01-03",
        "official_metadata_url": "https://www.spglobal.com/spdji/en/indices/equity/sp-500/?os=io___",
        "sha256": hashlib.sha256(raw.encode()).hexdigest(), "exclude_intraday": True,
    }
    # Validate both responses before replacing the saved files.
    temporary = raw_path.with_suffix(".json.tmp")
    temporary.write_text(raw, encoding="utf-8")
    temporary.replace(raw_path)
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(manifest_path)
    print(f"下載完成；只使用截至紐約日期 {cutoff} 的已收盤資料")


if __name__ == "__main__":
    main()
