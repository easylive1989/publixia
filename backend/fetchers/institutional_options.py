"""Three-major-investor options-positions fetcher.

Source: TAIFEX `三大法人 - 選擇權買賣權分計` daily download.

  POST https://www.taifex.com.tw/cht/3/callsAndPutsDateDown
  form: queryStartDate=YYYY/MM/DD, queryEndDate=YYYY/MM/DD, commodityId=

CSV layout mirrors the futures download but adds 買賣權別 (CALL/PUT)
and breaks 自營商 into 自營商(避險) + 自營商(自行買賣). For TXO we keep
all three identities (外資 / 投信 / 自營商) × CALL/PUT, summing the two
dealer sub-rows into a single 'dealer' identity so storage matches the
3 × 2 = 6-row-per-day shape the frontend expects.

Lazy fetch + DB cache, mirroring institutional_futures.py: on first run
we fall back INITIAL_LOOKBACK_DAYS days, on subsequent runs we only
chase the delta since the latest stored date. Like the futures
endpoint, multi-day spans return a DateTime error so we issue one
single-day request at a time, throttled to 2.0s.
"""
import csv
import io
import logging
import sys
import os
import time
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from repositories.institutional_options import (
    save_institutional_options_rows,
    get_latest_institutional_options_date,
)

logger = logging.getLogger(__name__)

TAIFEX_URL = "https://www.taifex.com.tw/cht/3/callsAndPutsDateDown"

# 商品名稱 → DB symbol. TXO only for now; extend here when adding more.
_PRODUCT_TO_SYMBOL = {
    "臺指選擇權": "TXO",
    "台指選擇權": "TXO",  # alt encoding
}

# 身份別 → canonical key. 自營商 has two sub-categories on TAIFEX
# downloads — both are mapped to 'dealer' and aggregated downstream.
_IDENTITY_TO_KEY = {
    "外資":             "foreign",
    "外資及陸資":       "foreign",
    "投信":             "investment_trust",
    "自營商":           "dealer",
    "自營商(避險)":     "dealer",
    "自營商(自行買賣)": "dealer",
}

# 買賣權別 → canonical CALL / PUT.
_PUT_CALL_TO_KEY = {
    "買權": "CALL", "CALL": "CALL", "Call": "CALL", "call": "CALL",
    "賣權": "PUT",  "PUT":  "PUT",  "Put":  "PUT",  "put":  "PUT",
}

INITIAL_LOOKBACK_DAYS = 365 * 5
BACKFILL_THROTTLE_SEC = 2.0
REQUEST_TIMEOUT = 30


# ── HTTP / parsing primitives ──────────────────────────────────────────

def _request_csv(start_date: str, end_date: str) -> str:
    """POST the form, return decoded CSV body."""
    form = {
        "queryStartDate": start_date.replace("-", "/"),
        "queryEndDate":   end_date.replace("-", "/"),
        "commodityId":    "",
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


def _to_float(s) -> float:
    if s is None:
        return 0.0
    s = str(s).strip().replace(",", "").replace(" ", "")
    if not s or s == "-":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _find_field(header: list[str], *needles: str) -> str | None:
    """Return the first header cell that contains ALL of `needles`."""
    for h in header:
        if all(n in h for n in needles):
            return h
    return None


def parse_csv(text: str) -> list[dict]:
    """Extract three-investor TXO rows from a TAIFEX daily options CSV.

    Returns a list of dicts shaped for `save_institutional_options_rows`,
    one entry per (date, symbol, identity, put_call). Dealer sub-rows
    are summed into a single 'dealer' row.
    """
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    header: list[str] | None = None
    header_idx = -1
    for i, row in enumerate(rows):
        if any("身份別" in (c or "") for c in row):
            header = [c.strip() for c in row]
            header_idx = i
            break
    if header is None:
        return []

    f_date         = _find_field(header, "日期")
    f_product      = _find_field(header, "商品名稱")
    f_put_call     = _find_field(header, "買賣權")
    f_identity     = _find_field(header, "身份別")
    # TAIFEX options report uses 買方/賣方 (terminology distinct from
    # the futures report's 多方/空方). Each side maps onto our long_oi /
    # short_oi columns: 買方 = open interest on the long side of the
    # contract, 賣方 = open interest on the short side.
    f_long_oi      = _find_field(header, "買方未平倉口數")
    f_short_oi     = _find_field(header, "賣方未平倉口數")
    f_long_amount  = _find_field(header, "買方未平倉契約金額")
    f_short_amount = _find_field(header, "賣方未平倉契約金額")

    required = (f_date, f_product, f_put_call, f_identity,
                f_long_oi, f_short_oi, f_long_amount, f_short_amount)
    if not all(required):
        logger.warning(
            "institutional_options parse: missing columns header=%r", header,
        )
        return []

    # Aggregate dealer sub-rows by accumulating into a dict keyed on
    # (date, symbol, identity, put_call).
    agg: dict[tuple, dict] = {}
    for row in rows[header_idx + 1:]:
        if len(row) < len(header):
            continue
        record = dict(zip(header, [c.strip() for c in row]))
        product   = (record.get(f_product) or "").strip()
        identity  = (record.get(f_identity) or "").strip()
        put_call  = (record.get(f_put_call) or "").strip()
        symbol    = _PRODUCT_TO_SYMBOL.get(product)
        ident_key = _IDENTITY_TO_KEY.get(identity)
        pc_key    = _PUT_CALL_TO_KEY.get(put_call)
        if symbol is None or ident_key is None or pc_key is None:
            continue
        date = _normalize_date(record.get(f_date) or "")
        if not date:
            continue
        key = (date, symbol, ident_key, pc_key)
        bucket = agg.get(key)
        if bucket is None:
            bucket = {
                "symbol":   symbol,
                "date":     date,
                "identity": ident_key,
                "put_call": pc_key,
                "long_oi":      0,
                "short_oi":     0,
                "long_amount":  0.0,
                "short_amount": 0.0,
            }
            agg[key] = bucket
        bucket["long_oi"]      += _to_int(record.get(f_long_oi))
        bucket["short_oi"]     += _to_int(record.get(f_short_oi))
        bucket["long_amount"]  += _to_float(record.get(f_long_amount))
        bucket["short_amount"] += _to_float(record.get(f_short_amount))

    return list(agg.values())


# ── Public entrypoints ────────────────────────────────────────────────

def fetch_for_date(date: str) -> int:
    """Fetch + persist one specific date. Returns rows saved (0 on
    holidays/weekends or when TAIFEX has not yet published the date).
    """
    text = _request_csv(date, date)
    parsed = parse_csv(text)
    if parsed:
        save_institutional_options_rows(parsed)
    logger.info(
        "institutional_options: %s → %d row(s) saved", date, len(parsed),
    )
    return len(parsed)


def fetch_for_range(start_date: str, end_date: str) -> int:
    """Iterate per trading day across [start, end]."""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d").date()
    if start_dt > end_dt:
        return 0

    total = 0
    cursor = start_dt
    while cursor <= end_dt:
        if cursor.weekday() >= 5:
            cursor += timedelta(days=1)
            continue
        d = cursor.strftime("%Y-%m-%d")
        try:
            total += fetch_for_date(d)
        except Exception as exc:           # noqa: BLE001
            logger.warning(
                "institutional_options fetch %s failed: %s", d, exc,
            )
        cursor += timedelta(days=1)
        if cursor <= end_dt:
            time.sleep(BACKFILL_THROTTLE_SEC)
    return total


def fetch_latest() -> bool:
    """Scheduler entry — fill in the gap between latest stored date and today."""
    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_institutional_options_date("TXO")

    if latest:
        latest_d = datetime.strptime(latest, "%Y-%m-%d").date()
        if latest_d >= today:
            return True
        # 7-day window absorbs late corrections.
        start = latest_d - timedelta(days=7)
    else:
        start = today - timedelta(days=INITIAL_LOOKBACK_DAYS)

    try:
        return fetch_for_range(start.strftime("%Y-%m-%d"), end_date) > 0
    except Exception as e:                 # noqa: BLE001
        logger.exception("institutional_options fetch_latest error: %s", e)
        return False


def backfill(start_date: str, end_date: str) -> int:
    """Manual backfill helper — same per-day iteration as fetch_for_range."""
    return fetch_for_range(start_date, end_date)
