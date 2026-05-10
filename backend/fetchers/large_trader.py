"""TAIFEX 大額交易人未沖銷部位結構表 fetcher (TX combined contract).

Source: TAIFEX `largeTraderFutDown` daily download.

  POST https://www.taifex.com.tw/cht/3/largeTraderFutDown
  form: queryStartDate=YYYY/MM/DD, queryEndDate=YYYY/MM/DD, contractId=

Unlike `futContractsDateDown`, this endpoint accepts multi-day query
spans, so we issue one request per backfill chunk rather than per day.

Response is a Big5 CSV. We keep only the row matching:
  商品(契約)   = "TX"        (combined entry: TX + MTX/4 + TMF/20)
  到期月份     = "999999"    (全部月份合計)
  交易人類別   = "0"         (全部交易人; "1" is 特定法人 only)

Used by `services.foreign_futures_metrics.compute_retail_ratio` to
derive 散戶多空比.
"""
import csv
import io
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from repositories.large_trader import (
    save_large_trader_rows,
    get_latest_large_trader_date,
)

logger = logging.getLogger(__name__)

TAIFEX_URL = "https://www.taifex.com.tw/cht/3/largeTraderFutDown"

INITIAL_LOOKBACK_DAYS = 365 * 5
REQUEST_TIMEOUT = 60
# Multi-day spans work, but we cap each request at ~6 months so a
# 5-year backfill stays well under the per-response size limits.
CHUNK_DAYS = 180
BACKFILL_THROTTLE_SEC = 1.0


# ── HTTP / parsing primitives ──────────────────────────────────────────

def _request_csv(start_date: str, end_date: str) -> str:
    form = {
        "queryStartDate": start_date.replace("-", "/"),
        "queryEndDate":   end_date.replace("-", "/"),
        "contractId":     "",
    }
    headers = {
        "User-Agent":
            "Mozilla/5.0 (compatible; publixia-stock-dashboard/1.0)",
    }
    r = requests.post(
        TAIFEX_URL, data=form, headers=headers, timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    raw = r.content
    try:
        return raw.decode("big5", errors="replace")
    except LookupError:                  # pragma: no cover
        return raw.decode("utf-8", errors="replace")


def _normalize_date(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _to_int(s) -> int:
    if s is None:
        return 0
    s = str(s).strip().replace(",", "").replace(" ", "")
    if not s or s == "-":
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def _find_field(header: list[str], *needles: str) -> str | None:
    for h in header:
        if all(n in h for n in needles):
            return h
    return None


def parse_csv(text: str) -> list[dict]:
    """Extract the TX/999999/type=0 rows from a TAIFEX large-trader CSV.

    Returns rows shaped for `save_large_trader_rows`.
    """
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    header: list[str] | None = None
    header_idx = -1
    for i, row in enumerate(rows):
        if any("交易人類別" in (c or "") for c in row):
            header = [c.strip() for c in row]
            header_idx = i
            break
    if header is None:
        return []

    f_date     = _find_field(header, "日期")
    f_product  = _find_field(header, "商品")
    f_month    = _find_field(header, "到期月份")
    f_type     = _find_field(header, "交易人類別")
    f_top5_l   = _find_field(header, "前五大", "買")
    f_top5_s   = _find_field(header, "前五大", "賣")
    f_top10_l  = _find_field(header, "前十大", "買")
    f_top10_s  = _find_field(header, "前十大", "賣")
    f_market   = _find_field(header, "全市場")

    required = (f_date, f_product, f_month, f_type,
                f_top5_l, f_top5_s, f_top10_l, f_top10_s, f_market)
    if not all(required):
        logger.warning(
            "large_trader parse: missing columns header=%r", header,
        )
        return []

    out: list[dict] = []
    for row in rows[header_idx + 1:]:
        if len(row) < len(header):
            continue
        record = dict(zip(header, [c.strip() for c in row]))
        product = (record.get(f_product) or "").strip()
        month   = (record.get(f_month)   or "").strip()
        ttype   = (record.get(f_type)    or "").strip()
        if product != "TX" or month != "999999" or ttype != "0":
            continue
        date = _normalize_date(record.get(f_date) or "")
        if not date:
            continue
        out.append({
            "date":           date,
            "market_oi":      _to_int(record.get(f_market)),
            "top5_long_oi":   _to_int(record.get(f_top5_l)),
            "top5_short_oi":  _to_int(record.get(f_top5_s)),
            "top10_long_oi":  _to_int(record.get(f_top10_l)),
            "top10_short_oi": _to_int(record.get(f_top10_s)),
        })
    return out


# ── Public entrypoints ────────────────────────────────────────────────

def fetch_for_range(start_date: str, end_date: str) -> int:
    """Iterate in CHUNK_DAYS-sized windows. Returns total rows saved."""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d").date()
    if start_dt > end_dt:
        return 0

    total = 0
    cursor = start_dt
    while cursor <= end_dt:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS - 1), end_dt)
        s = cursor.strftime("%Y-%m-%d")
        e = chunk_end.strftime("%Y-%m-%d")
        try:
            text = _request_csv(s, e)
            parsed = parse_csv(text)
            if parsed:
                save_large_trader_rows(parsed)
            total += len(parsed)
            logger.info(
                "large_trader: %s..%s → %d row(s) saved", s, e, len(parsed),
            )
        except Exception as exc:           # noqa: BLE001
            logger.warning("large_trader fetch %s..%s failed: %s", s, e, exc)
        cursor = chunk_end + timedelta(days=1)
        if cursor <= end_dt:
            time.sleep(BACKFILL_THROTTLE_SEC)
    return total


def fetch_latest() -> bool:
    """Scheduler entry — fill the gap between latest stored date and today.

    On first run, falls back INITIAL_LOOKBACK_DAYS days.
    """
    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_large_trader_date()
    if latest:
        latest_d = datetime.strptime(latest, "%Y-%m-%d").date()
        if latest_d >= today:
            return True
        # Re-fetch a 7-day window to absorb late corrections.
        start = latest_d - timedelta(days=7)
    else:
        start = today - timedelta(days=INITIAL_LOOKBACK_DAYS)

    try:
        return fetch_for_range(start.strftime("%Y-%m-%d"), end_date) > 0
    except Exception as e:                 # noqa: BLE001
        logger.exception("large_trader fetch_latest error: %s", e)
        return False


def backfill(start_date: str, end_date: str) -> int:
    return fetch_for_range(start_date, end_date)
