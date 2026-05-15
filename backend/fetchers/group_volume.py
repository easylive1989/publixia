"""TWSE industry-level daily volume aggregation.

Each evening after market close, pulls per-stock OHLCV from FinMind
(`TaiwanStockPrice`), joins to the industry classification from
`TaiwanStockInfo`, and writes rolled-up per-industry rows into
`group_volume_daily`. ETFs / ETNs / 受益證券 / 存託憑證 / Index trackers
are skipped — "族群" only means common-stock industries here.
"""
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.finmind import request
from repositories.group_volume import save_group_volume_batch


EXCLUDED_INDUSTRIES = {"ETF", "ETN", "受益證券", "存託憑證", "Index", ""}


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


def _aggregate_by_date_industry(
    rows: list[dict], industry_map: dict[str, str],
) -> dict[str, dict[str, dict]]:
    """``rows`` (raw FinMind price rows) → ``{date: {industry: bucket}}``."""
    out: dict[str, dict[str, dict]] = {}
    for row in rows:
        d = row.get("date")
        industry = industry_map.get(row.get("stock_id"))
        if not d or not industry:
            continue
        b = out.setdefault(d, {}).setdefault(industry, {
            "total_value":  0.0,
            "total_volume": 0,
            "stock_count":  0,
        })
        b["total_value"]  += float(row.get("Trading_money") or 0)
        b["total_volume"] += int(row.get("Trading_Volume")  or 0)
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
    list when FinMind has no rows for the date (weekend / holiday / not
    yet published).
    """
    industry_map = _load_industry_map()
    rows = request("TaiwanStockPrice", start_date=target_date, end_date=target_date)
    by_date = _aggregate_by_date_industry(rows, industry_map)
    return _buckets_to_aggregates(by_date.get(target_date, {}))


def fetch_industry_volume_range(
    start_date: str, end_date: str,
) -> dict[str, list[dict]]:
    """Iterate days from ``start_date`` to ``end_date`` (inclusive) and
    aggregate per-industry totals for each.

    FinMind's ``TaiwanStockPrice`` endpoint rejects multi-day range queries
    when no ``data_id`` is supplied (HTTP 400), so we hit it once per
    calendar day. The industry map is loaded once and reused across calls.
    Weekend / holiday days return empty FinMind responses and are silently
    skipped. Per-day FinMind errors are logged and skipped so a single
    bad day doesn't abort the whole backfill.
    """
    industry_map = _load_industry_map()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d").date()

    result: dict[str, list[dict]] = {}
    cursor = start_dt
    while cursor <= end_dt:
        date_str = cursor.strftime("%Y-%m-%d")
        try:
            rows = request(
                "TaiwanStockPrice",
                start_date=date_str,
                end_date=date_str,
            )
        except Exception as e:
            print(f"[group_volume] skip {date_str}: {e}")
            cursor += timedelta(days=1)
            continue
        by_date = _aggregate_by_date_industry(rows, industry_map)
        for d, buckets in by_date.items():
            result[d] = _buckets_to_aggregates(buckets)
        cursor += timedelta(days=1)
    return result


def run_industry_for_today() -> int:
    """Scheduler entry — aggregate today (TST) and persist."""
    today_tst = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
    aggregates = fetch_industry_volume(today_tst)
    n = save_group_volume_batch(today_tst, "industry", aggregates)
    print(f"[group_volume] industry {today_tst}: {n} groups saved")
    return n
