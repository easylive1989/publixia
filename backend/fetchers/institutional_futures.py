"""Foreign-investor futures positions fetcher.

Source: TAIFEX `三大法人 - 區分各期貨契約` daily download.

  POST https://www.taifex.com.tw/cht/3/futContractsDateDown
  form: queryStartDate=YYYY/MM/DD, queryEndDate=YYYY/MM/DD, commodityId=

The response is a Big5 (or sometimes UTF-8) CSV; we look up columns by
header name rather than position so the parser survives minor schema
shifts (TAIFEX has occasionally added/removed a 序號 column).

Each request returns 3 身份別 (自營商 / 投信 / 外資) × N 商品 rows. We
keep only 外資 rows for 臺股期貨 (TX) and 小型臺指期貨 (MTX); the
result is upserted into `institutional_futures_daily`.

Lazy fetch + DB cache, mirroring the futures.py pattern: on first run we
fall back ``INITIAL_LOOKBACK_DAYS`` days (default 5 years), on
subsequent runs we only chase the delta since the latest stored date.
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
from repositories.institutional_futures import (
    save_institutional_futures_rows,
    get_latest_institutional_futures_date,
)

logger = logging.getLogger(__name__)

TAIFEX_URL = "https://www.taifex.com.tw/cht/3/futContractsDateDown"

# 商品名稱 → DB symbol
_PRODUCT_TO_SYMBOL = {
    "臺股期貨":     "TX",
    "台股期貨":     "TX",     # alt encoding seen in archives
    "小型臺指期貨": "MTX",
    "小型台指期貨": "MTX",
}

_FOREIGN_LABELS = {"外資", "外資及陸資"}  # post-2020 label includes 陸資

INITIAL_LOOKBACK_DAYS = 365 * 5
# TAIFEX `futContractsDateDown` rejects multi-day query spans whose
# end date is too close to today (it returns an HTML page with a
# "DateTime error" JS alert). Empirically the only span that always
# works is single-day, so we issue one request per trading day.
# 2.0s between requests is comfortably inside the rate limit; weekends
# are skipped client-side so a 5-year backfill is ~22 minutes.
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
    # TAIFEX serves Big5 (CP950) on this endpoint; decode with replace so
    # the parser doesn't crash on the rare invalid byte.
    raw = r.content
    try:
        return raw.decode("big5", errors="replace")
    except LookupError:                  # pragma: no cover — codec always present
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
    """Extract foreign-investor TX/MTX rows from a TAIFEX daily CSV.

    Returns a list of dicts shaped for `save_institutional_futures_rows`.
    """
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    # Find the header row — TAIFEX prefixes the file with a couple of
    # title lines, so the actual header is the first row containing the
    # 身份別 column.
    header: list[str] | None = None
    header_idx = -1
    for i, row in enumerate(rows):
        if any("身份別" in (c or "") for c in row):
            header = [c.strip() for c in row]
            header_idx = i
            break
    if header is None:
        return []

    f_date           = _find_field(header, "日期")
    f_product        = _find_field(header, "商品名稱")
    f_identity       = _find_field(header, "身份別")
    f_long_oi        = _find_field(header, "多方未平倉口數")
    f_short_oi       = _find_field(header, "空方未平倉口數")
    f_long_amount    = _find_field(header, "多方未平倉契約金額")
    f_short_amount   = _find_field(header, "空方未平倉契約金額")

    required = (f_date, f_product, f_identity, f_long_oi, f_short_oi,
                f_long_amount, f_short_amount)
    if not all(required):
        logger.warning(
            "institutional_futures parse: missing columns header=%r", header,
        )
        return []

    out: list[dict] = []
    for row in rows[header_idx + 1:]:
        if len(row) < len(header):
            continue
        record = dict(zip(header, [c.strip() for c in row]))
        product = (record.get(f_product) or "").strip()
        identity = (record.get(f_identity) or "").strip()
        symbol = _PRODUCT_TO_SYMBOL.get(product)
        if symbol is None or identity not in _FOREIGN_LABELS:
            continue
        date = _normalize_date(record.get(f_date) or "")
        if not date:
            continue
        out.append({
            "symbol": symbol,
            "date":   date,
            "foreign_long_oi":      _to_int(record.get(f_long_oi)),
            "foreign_short_oi":     _to_int(record.get(f_short_oi)),
            "foreign_long_amount":  _to_float(record.get(f_long_amount)),
            "foreign_short_amount": _to_float(record.get(f_short_amount)),
        })
    return out


# ── Public entrypoints ────────────────────────────────────────────────

def fetch_for_date(date: str) -> int:
    """Fetch + persist one specific date. Returns rows saved (0 on
    holidays/weekends or when TAIFEX has not yet published the date).
    """
    text = _request_csv(date, date)
    parsed = parse_csv(text)
    if parsed:
        save_institutional_futures_rows(parsed)
    logger.info(
        "institutional_futures: %s → %d row(s) saved", date, len(parsed),
    )
    return len(parsed)


def fetch_for_range(start_date: str, end_date: str) -> int:
    """Iterate per trading day across [start, end].

    TAIFEX's `futContractsDateDown` rejects multi-day query spans, so
    we walk the range one day at a time. Saturdays/Sundays are skipped
    client-side to cut request volume; non-trading weekdays simply
    return 0 rows from TAIFEX and roll on.
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d").date()
    if start_dt > end_dt:
        return 0

    total = 0
    cursor = start_dt
    while cursor <= end_dt:
        # Skip weekends — TAIFEX has no data for Sat/Sun and the
        # request just wastes throttle budget.
        if cursor.weekday() >= 5:
            cursor += timedelta(days=1)
            continue
        d = cursor.strftime("%Y-%m-%d")
        try:
            total += fetch_for_date(d)
        except Exception as exc:           # noqa: BLE001
            logger.warning(
                "institutional_futures fetch %s failed: %s", d, exc,
            )
        cursor += timedelta(days=1)
        if cursor <= end_dt:
            time.sleep(BACKFILL_THROTTLE_SEC)
    return total


def fetch_latest() -> bool:
    """Scheduler entry — fill in the gap between latest stored date and today.

    Picks the lagging symbol (TX vs MTX) so neither falls behind. On
    first run, falls back INITIAL_LOOKBACK_DAYS days.
    """
    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest_tx  = get_latest_institutional_futures_date("TX")
    latest_mtx = get_latest_institutional_futures_date("MTX")
    latest = min((d for d in (latest_tx, latest_mtx) if d), default=None)

    if latest:
        latest_d = datetime.strptime(latest, "%Y-%m-%d").date()
        if latest_d >= today:
            return True
        # Re-fetch a 7-day window to absorb any late corrections.
        start = latest_d - timedelta(days=7)
    else:
        start = today - timedelta(days=INITIAL_LOOKBACK_DAYS)

    try:
        return fetch_for_range(start.strftime("%Y-%m-%d"), end_date) > 0
    except Exception as e:                 # noqa: BLE001 — keep scheduler alive
        logger.exception("institutional_futures fetch_latest error: %s", e)
        return False


def backfill(start_date: str, end_date: str) -> int:
    """Manual backfill helper — same per-day iteration as fetch_for_range.

    Use from the scripts/ entrypoint when bringing a fresh DB online.
    """
    return fetch_for_range(start_date, end_date)
