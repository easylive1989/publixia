"""TWSE 集中市場成交統計（FMTQIK）helper.

One endpoint, one month per request: date / 成交股數 / 成交金額 / 成交筆數 /
發行量加權股價指數 / 漲跌點數 for every trading day of the month. No token
needed. Dates come back in ROC format (``115/07/01``) and numbers with
thousands separators — both normalised here so callers get clean rows.
"""
import logging
from datetime import date

import requests

from core.errors import FetcherError, FetcherParseError

logger = logging.getLogger(__name__)

URL = "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK"
_HEADERS = {"User-Agent": "Mozilla/5.0 (stock-dashboard market sync)"}

# 成交金額 arrives in NT$ (元); the sheet/UI unit is 億元.
_YI = 1e8


def _roc_to_iso(roc: str) -> str:
    """``115/07/01`` → ``2026-07-01``."""
    y, m, d = roc.strip().split("/")
    return f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"


def _num(s: str) -> float:
    return float(str(s).replace(",", "").strip())


def fetch_month(year: int, month: int) -> list[dict]:
    """Fetch one month of daily market totals.

    Returns ``[{date, index_close, turnover}, ...]`` (turnover in 億元),
    empty list for months TWSE has no data for (future / pre-1999).
    """
    params = {"date": f"{year:04d}{month:02d}01", "response": "json"}
    try:
        r = requests.get(URL, params=params, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError) as e:
        raise FetcherError(f"TWSE FMTQIK {year}-{month:02d}: {e}") from e

    if payload.get("stat") != "OK":
        # "很抱歉，沒有符合條件的資料!" — month with no data, not an error.
        return []

    rows: list[dict] = []
    for raw in payload.get("data") or []:
        try:
            rows.append({
                "date": _roc_to_iso(raw[0]),
                "index_close": _num(raw[4]),
                "turnover": _num(raw[2]) / _YI,
            })
        except (IndexError, ValueError) as e:
            raise FetcherParseError(
                f"TWSE FMTQIK row malformed {raw!r}: {e}"
            ) from e
    return rows


def month_range(start: date, end: date) -> list[tuple[int, int]]:
    """Inclusive list of (year, month) from ``start``'s month to ``end``'s."""
    months: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months
