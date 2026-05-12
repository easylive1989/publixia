"""TAIFEX 選擇權每日交易行情 — per-strike OI fetcher.

Source: TAIFEX `dlOptDataDown` daily CSV (the same export driving the
public 「每日選擇權市場成交資訊」 page).

  POST https://www.taifex.com.tw/cht/3/dlOptDataDown
  form: queryStartDate=YYYY/MM/DD, queryEndDate=YYYY/MM/DD,
        commodity_id=TXO

Each row in the CSV is one (商品代號, 到期月份(週別), 履約價, 買賣權,
交易時段) tuple. We keep only TXO 一般 (regular session) rows since
盤後 (after-hours) rows duplicate the same OI count.

Lazy-fetch behaviour mirrors fetchers.institutional_options: on first
run we backfill INITIAL_LOOKBACK_DAYS, on subsequent runs we only chase
the delta since the latest stored date, single-day-at-a-time, throttled
at 2.0s between requests to stay polite with TAIFEX.
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
from repositories.txo_strike_oi import (
    save_txo_strike_oi_rows,
    get_latest_txo_strike_oi_date,
)

logger = logging.getLogger(__name__)

TAIFEX_URL = "https://www.taifex.com.tw/cht/3/dlOptDataDown"

# 商品代號 → DB symbol. Limit to TXO; the CSV may contain other option
# products if commodity_id is left empty, so we filter explicitly.
_PRODUCT_TO_SYMBOL = {
    "TXO": "TXO",
    "臺指選擇權": "TXO",
    "台指選擇權": "TXO",
}

_PUT_CALL_TO_KEY = {
    "買權": "CALL", "CALL": "CALL", "Call": "CALL", "call": "CALL",
    "賣權": "PUT",  "PUT":  "PUT",  "Put":  "PUT",  "put":  "PUT",
}

# 交易時段 we accept. TAIFEX repeats most fields between 一般 and
# 盤後 rows; OI is identical on both, so we keep only one to avoid
# double counting.
_SESSION_REGULAR = ("一般", "Regular", "")

# Backfill knobs — strike data is huge (~3k rows/day), so start with a
# shorter horizon than institutional_options' 5-year window. Operators
# can extend via the admin backfill helper.
INITIAL_LOOKBACK_DAYS = 365
BACKFILL_THROTTLE_SEC = 2.0
REQUEST_TIMEOUT = 30


# ── HTTP / parsing primitives ──────────────────────────────────────────

def _request_csv(start_date: str, end_date: str) -> str:
    # `down_type=1` selects the CSV download mode; without it TAIFEX
    # returns 200 OK with an empty body. `commodity_id2` is the stock-
    # options sub-product slot — sent empty to mirror the live form.
    form = {
        "down_type":      "1",
        "commodity_id":   "TXO",
        "commodity_id2":  "",
        "queryStartDate": start_date.replace("-", "/"),
        "queryEndDate":   end_date.replace("-", "/"),
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
    except LookupError:                      # pragma: no cover
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


def _to_float_opt(s) -> float | None:
    if s is None:
        return None
    s = str(s).strip().replace(",", "").replace(" ", "")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _find_field(header: list[str], *needles: str) -> str | None:
    for h in header:
        if all(n in h for n in needles):
            return h
    return None


def parse_csv(text: str) -> list[dict]:
    """Extract per-strike OI rows from a TAIFEX option daily CSV.

    Returns a list of dicts shaped for `save_txo_strike_oi_rows`. Only
    TXO 一般 session rows are kept, deduped on
    (date, expiry_month, strike, put_call).
    """
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    header: list[str] | None = None
    header_idx = -1
    # TAIFEX header line contains 履約價; use that as a strong anchor.
    for i, row in enumerate(rows):
        if any("履約價" in (c or "") for c in row):
            header = [c.strip() for c in row]
            header_idx = i
            break
    if header is None:
        return []
    # TAIFEX's real CSV header ends with a trailing comma, producing an
    # extra empty cell vs. the data rows. Strip trailing empty header
    # cells so the row-length check below doesn't reject every row.
    while header and header[-1] == "":
        header.pop()

    f_date     = _find_field(header, "日期")
    f_product  = _find_field(header, "契約")
    if f_product is None:
        f_product = _find_field(header, "商品")
    f_expiry   = _find_field(header, "到期月份")
    f_strike   = _find_field(header, "履約價")
    f_put_call = _find_field(header, "買賣權")
    # 未沖銷契約量 ≡ open interest in TAIFEX's terminology.
    f_oi       = _find_field(header, "未沖銷")
    if f_oi is None:
        f_oi   = _find_field(header, "未平倉")
    f_settle   = _find_field(header, "結算價")
    f_session  = _find_field(header, "交易時段")

    required = (f_date, f_product, f_expiry, f_strike, f_put_call, f_oi)
    if not all(required):
        logger.warning(
            "txo_strike_oi parse: missing columns header=%r", header,
        )
        return []

    # Dedup on (date, expiry, strike, put_call) — a CSV may contain
    # both 一般/盤後 rows; we keep the first 一般 (or first overall if
    # session column is absent).
    agg: dict[tuple, dict] = {}
    for row in rows[header_idx + 1:]:
        if len(row) < len(header):
            continue
        rec = dict(zip(header, [c.strip() for c in row]))
        product = (rec.get(f_product) or "").strip()
        symbol  = _PRODUCT_TO_SYMBOL.get(product)
        if symbol is None:
            continue
        if f_session is not None:
            sess = (rec.get(f_session) or "").strip()
            if sess not in _SESSION_REGULAR:
                continue
        pc_key = _PUT_CALL_TO_KEY.get((rec.get(f_put_call) or "").strip())
        if pc_key is None:
            continue
        date = _normalize_date(rec.get(f_date) or "")
        if not date:
            continue
        strike_raw = (rec.get(f_strike) or "").replace(",", "").strip()
        if not strike_raw or strike_raw == "-":
            continue
        try:
            strike = float(strike_raw)
        except ValueError:
            continue
        expiry = (rec.get(f_expiry) or "").strip()
        if not expiry:
            continue
        key = (date, expiry, strike, pc_key)
        if key in agg:
            continue
        agg[key] = {
            "symbol":        symbol,
            "date":          date,
            "expiry_month":  expiry,
            "strike":        strike,
            "put_call":      pc_key,
            "open_interest": _to_int(rec.get(f_oi)),
            "settle_price":  _to_float_opt(rec.get(f_settle)) if f_settle else None,
        }
    return list(agg.values())


# ── Public entrypoints ────────────────────────────────────────────────

def fetch_for_date(date: str) -> int:
    text = _request_csv(date, date)
    # Header anchor must be present even on a non-trading day (TAIFEX
    # returns the CSV header alone with no data rows for weekends/
    # holidays). Its absence means upstream returned an error page —
    # raise so the scheduler records last_status=error instead of
    # silently parking forever on 0 rows.
    if "履約價" not in text:
        raise RuntimeError(
            f"txo_strike_oi: TAIFEX response for {date} is missing "
            f"the '履約價' header anchor (likely HTML/error page); "
            f"first 200 chars: {text[:200]!r}"
        )
    parsed = parse_csv(text)
    if parsed:
        save_txo_strike_oi_rows(parsed)
    logger.info(
        "txo_strike_oi: %s → %d row(s) saved", date, len(parsed),
    )
    return len(parsed)


def fetch_for_range(start_date: str, end_date: str) -> int:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d").date()
    if start_dt > end_dt:
        return 0

    total = 0
    attempted = 0
    failed = 0
    last_err: Exception | None = None
    cursor = start_dt
    while cursor <= end_dt:
        if cursor.weekday() >= 5:
            cursor += timedelta(days=1)
            continue
        d = cursor.strftime("%Y-%m-%d")
        attempted += 1
        try:
            total += fetch_for_date(d)
        except Exception as exc:               # noqa: BLE001
            failed += 1
            last_err = exc
            logger.warning(
                "txo_strike_oi fetch %s failed: %s", d, exc,
            )
        cursor += timedelta(days=1)
        if cursor <= end_dt:
            time.sleep(BACKFILL_THROTTLE_SEC)
    # If every attempted day failed, escalate — the upstream is likely
    # broken (URL changed, network down) and the scheduler should mark
    # this run as error rather than silently parking on 0 rows.
    if attempted > 0 and failed == attempted:
        raise RuntimeError(
            f"txo_strike_oi: all {attempted} day(s) in "
            f"{start_date}..{end_date} failed; last error: {last_err}"
        ) from last_err
    return total


def fetch_latest() -> bool:
    """Scheduler entry — fill gap between latest stored date and today.

    Exceptions propagate to the scheduler wrapper so a broken upstream
    surfaces as last_status=error in the admin CLI rather than silently
    succeeding on zero rows (sibling fetchers swallow errors here; we
    chose not to because TAIFEX is this job's only data source).
    """
    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_txo_strike_oi_date("TXO")
    if latest:
        latest_d = datetime.strptime(latest, "%Y-%m-%d").date()
        if latest_d >= today:
            return True
        start = latest_d - timedelta(days=7)
    else:
        start = today - timedelta(days=INITIAL_LOOKBACK_DAYS)

    return fetch_for_range(start.strftime("%Y-%m-%d"), end_date) > 0


def backfill(start_date: str, end_date: str) -> int:
    return fetch_for_range(start_date, end_date)
