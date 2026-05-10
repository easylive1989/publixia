"""TX futures final-settlement date fetcher.

Two strategies, used together:

1. **Scrape TAIFEX** `fSPRecord` (final-settlement-price record) page —
   this is the authoritative source for *past* settlement dates,
   accounting for holiday roll-forward.
2. **Algorithmic fallback** — TX settles on the third Wednesday of each
   delivery month. Used for months not yet covered by the scrape (e.g.
   forward months that haven't settled yet) and as a safety net when
   scraping fails entirely.

The result feeds `futures_settlement_dates`, which the foreign-flow
chart reads to render `結算日` markers on the K-line.
"""
import calendar
import logging
import re
import sys
import os
from datetime import date, datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from repositories.institutional_futures import save_settlement_dates

logger = logging.getLogger(__name__)

TAIFEX_FSP_URL = "https://www.taifex.com.tw/cht/5/fSPRecord"
REQUEST_TIMEOUT = 30

# Match a TAIFEX FSP table row: 結算月份 cell + 最後結算日 cell.
# Tolerant of whitespace/attribute noise inside the <td>.
_FSP_ROW_RE = re.compile(
    r"<td[^>]*>\s*(\d{4})/(\d{2})\s*</td>"
    r"\s*<td[^>]*>\s*(\d{4})/(\d{2})/(\d{2})\s*</td>",
    re.IGNORECASE,
)


# ── Algorithmic generator ──────────────────────────────────────────────

def third_wednesday(year: int, month: int) -> date:
    """The third Wednesday of (year, month).

    Holidays shift TAIFEX settlement forward in practice; the scraping
    path above will overwrite any algorithm-generated row that turns
    out to be off.
    """
    first = date(year, month, 1)
    # Mon=0 ... Sun=6; Wednesday=2
    offset_to_first_wed = (2 - first.weekday()) % 7
    first_wed = first + timedelta(days=offset_to_first_wed)
    return first_wed + timedelta(days=14)


def generate_algorithmic(
    start: date, end: date,
) -> list[dict]:
    """All third-Wednesday dates whose settlement date is in [start, end]."""
    out: list[dict] = []
    y, m = start.year, start.month
    while True:
        sd = third_wednesday(y, m)
        if sd > end:
            break
        if sd >= start:
            out.append({
                "year_month":      f"{y:04d}-{m:02d}",
                "settlement_date": sd.strftime("%Y-%m-%d"),
            })
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


# ── TAIFEX scraper ─────────────────────────────────────────────────────

def _scrape_fsp(start_date: str, end_date: str) -> list[dict]:
    """Scrape TAIFEX fSPRecord page for [start, end]; raise on HTTP error."""
    form = {
        "MarketCode":     "0",
        "commodity_id2":  "TX",
        "queryStartDate": start_date.replace("-", "/"),
        "queryEndDate":   end_date.replace("-", "/"),
    }
    headers = {
        "User-Agent":
            "Mozilla/5.0 (compatible; publixia-stock-dashboard/1.0)",
    }
    r = requests.post(
        TAIFEX_FSP_URL, data=form, headers=headers, timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    # TAIFEX content-type can lie; let requests guess and fall through.
    text = r.text
    items: list[dict] = []
    for ym_y, ym_m, d_y, d_m, d_d in _FSP_ROW_RE.findall(text):
        items.append({
            "year_month":      f"{ym_y}-{ym_m}",
            "settlement_date": f"{d_y}-{d_m}-{d_d}",
        })
    return items


# ── Public entrypoints ────────────────────────────────────────────────

def fetch_settlement_dates(
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    forward_months: int = 12,
) -> int:
    """Backfill historical + forward TX settlement dates.

    Defaults: 5 years back from today through `forward_months` ahead.
    Forward months are always algorithmic (TAIFEX hasn't published them
    yet); historical months prefer the scraped value, fall back to the
    algorithm if scraping yields nothing.
    """
    today = datetime.now(timezone.utc).astimezone().date()
    if not start_date:
        start_date = (today - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
    if not end_date:
        # forward_months later, snapped to the end of that month so we
        # always include that month's third Wednesday.
        y = today.year
        m = today.month + forward_months
        while m > 12:
            m -= 12
            y += 1
        last_day = calendar.monthrange(y, m)[1]
        end_date = date(y, m, last_day).strftime("%Y-%m-%d")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d").date()

    # Algorithm seed for the entire range.
    algorithmic = {
        item["year_month"]: item for item in generate_algorithmic(start_dt, end_dt)
    }

    # Scrape attempts — TAIFEX caps query span at 1 year-ish in practice;
    # walk year-by-year. Past-only because future months aren't published.
    today_str = today.strftime("%Y-%m-%d")
    scrape_end = min(end_date, today_str)
    if scrape_end >= start_date:
        cursor = start_dt
        scrape_end_dt = datetime.strptime(scrape_end, "%Y-%m-%d").date()
        while cursor <= scrape_end_dt:
            window_end = min(date(cursor.year, 12, 31), scrape_end_dt)
            try:
                items = _scrape_fsp(
                    cursor.strftime("%Y-%m-%d"),
                    window_end.strftime("%Y-%m-%d"),
                )
            except Exception as e:           # noqa: BLE001
                logger.warning(
                    "futures_settlement scrape %s~%s failed: %s — using algorithm",
                    cursor, window_end, e,
                )
                items = []
            for it in items:
                algorithmic[it["year_month"]] = it    # scrape overrides algo
            cursor = date(cursor.year + 1, 1, 1)

    final = list(algorithmic.values())
    save_settlement_dates("TX", final)
    logger.info(
        "futures_settlement: %s~%s → %d month(s) saved",
        start_date, end_date, len(final),
    )
    return len(final)


def fetch_settlement_refresh() -> bool:
    """Scheduler entry — refresh the upcoming 12 months."""
    try:
        fetch_settlement_dates()
    except Exception as e:                   # noqa: BLE001 — keep scheduler alive
        logger.exception("futures_settlement refresh error: %s", e)
        return False
    return True
