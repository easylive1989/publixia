"""TWSE industry-level daily volume aggregation.

Each evening after market close, pulls per-stock 成交股數/成交金額 from
TWSE「每日收盤行情(全部)」(`MI_INDEX` endpoint), joins to the industry
classification from FinMind `TaiwanStockInfo`, and writes rolled-up
per-industry rows into `group_volume_daily`. ETFs / ETNs / 受益證券 /
存託憑證 / Index trackers are skipped — "族群" only means common-stock
industries here.

FinMind `TaiwanStockPrice`'s "整日全市場" variant requires a Backer/Sponsor
tier; TWSE's MI_INDEX is free and serves the same numbers.
"""
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.finmind import request
from repositories.group_volume import save_group_volume_batch


EXCLUDED_INDUSTRIES = {"ETF", "ETN", "受益證券", "存託憑證", "Index", ""}

TWSE_DAILY_ALL_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"


def _fetch_twse_daily_all(date_str: str) -> list[dict]:
    """Pull TWSE「每日收盤行情(全部)」for one calendar day.

    Returns ``[{stock_id, trading_volume, trading_money}, ...]`` (one row
    per listed security that traded). Empty list when TWSE has no data
    for the date (weekend / holiday / not yet published).

    Used because FinMind ``TaiwanStockPrice`` without ``data_id`` requires
    a Backer/Sponsor tier — TWSE's MI_INDEX endpoint is free.
    """
    params = {
        "date":     date_str.replace("-", ""),
        "type":     "ALL",
        "response": "json",
    }
    r = requests.get(TWSE_DAILY_ALL_URL, params=params, timeout=20)
    r.raise_for_status()
    payload = r.json()
    if payload.get("stat") != "OK":
        return []
    for table in payload.get("tables") or []:
        if "每日收盤行情" not in (table.get("title") or ""):
            continue
        fields = table.get("fields") or []
        try:
            i_id  = fields.index("證券代號")
            i_vol = fields.index("成交股數")
            i_val = fields.index("成交金額")
        except ValueError:
            return []
        out: list[dict] = []
        for row in table.get("data") or []:
            try:
                out.append({
                    "stock_id":       row[i_id],
                    "trading_volume": int((row[i_vol] or "0").replace(",", "")),
                    "trading_money":  int((row[i_val] or "0").replace(",", "")),
                })
            except (ValueError, IndexError):
                continue
        return out
    return []


def _load_industry_map() -> dict[str, str]:
    """Return ``{stock_id: industry_category}`` for TWSE common stocks."""
    rows = request("TaiwanStockInfo", start_date="2020-01-01")
    out: dict[str, str] = {}
    for r in rows:
        if r.get("type") != "twse":
            continue
        industry = r.get("industry_category")
        if industry is None or industry in EXCLUDED_INDUSTRIES:
            continue
        sid = r.get("stock_id")
        if sid:
            out[sid] = industry
    return out


def _aggregate_for_industries(
    twse_rows: list[dict], industry_map: dict[str, str],
) -> dict[str, dict]:
    """One day of TWSE rows → ``{industry: bucket}``.

    Securities whose ``stock_id`` is not in ``industry_map`` (ETFs, warrants,
    OTC, blanks, …) are silently dropped — that's how non-stock listings
    get filtered out.
    """
    out: dict[str, dict] = {}
    for row in twse_rows:
        industry = industry_map.get(row.get("stock_id"))
        if not industry:
            continue
        b = out.setdefault(industry, {
            "total_value":  0.0,
            "total_volume": 0,
            "stock_count":  0,
        })
        b["total_value"]  += float(row.get("trading_money")  or 0)
        b["total_volume"] += int(row.get("trading_volume") or 0)
        b["stock_count"]  += 1
    return out


def _buckets_to_aggregates(buckets: dict[str, dict]) -> list[dict]:
    return [
        {"group_code": ind, "group_name": ind, **vals}
        for ind, vals in buckets.items()
    ]


def fetch_industry_volume(target_date: str) -> list[dict]:
    """Aggregate per-industry totals for one trading day.

    Returns a list of ``{group_code, group_name, total_value, total_volume,
    stock_count}`` dicts (one per industry that traded that day). Empty
    list when TWSE has no rows for the date (weekend / holiday / not yet
    published).
    """
    industry_map = _load_industry_map()
    twse_rows = _fetch_twse_daily_all(target_date)
    return _buckets_to_aggregates(_aggregate_for_industries(twse_rows, industry_map))


def fetch_industry_volume_range(
    start_date: str, end_date: str,
) -> dict[str, list[dict]]:
    """Iterate days from ``start_date`` to ``end_date`` (inclusive) and
    aggregate per-industry totals for each.

    The industry map is loaded once and reused across calls. Weekend /
    holiday days return empty TWSE responses and are silently skipped.
    Per-day errors are logged and skipped so one bad day doesn't abort the
    whole backfill. A short sleep between requests keeps TWSE from
    rate-limiting longer ranges.
    """
    industry_map = _load_industry_map()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d").date()

    result: dict[str, list[dict]] = {}
    cursor = start_dt
    while cursor <= end_dt:
        date_str = cursor.strftime("%Y-%m-%d")
        try:
            twse_rows = _fetch_twse_daily_all(date_str)
        except Exception as e:
            print(f"[group_volume] skip {date_str}: {e}")
            cursor += timedelta(days=1)
            time.sleep(0.3)
            continue
        buckets = _aggregate_for_industries(twse_rows, industry_map)
        if buckets:
            result[date_str] = _buckets_to_aggregates(buckets)
        cursor += timedelta(days=1)
        time.sleep(0.3)
    return result


def run_industry_for_today() -> int:
    """Scheduler entry — aggregate today (TST) and persist."""
    today_tst = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
    aggregates = fetch_industry_volume(today_tst)
    n = save_group_volume_batch(today_tst, "industry", aggregates)
    print(f"[group_volume] industry {today_tst}: {n} groups saved")
    return n
