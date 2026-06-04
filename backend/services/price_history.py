"""Stock price windows via yfinance (no API token needed).

Given a post's date and a stock, compute the entry price (post-day close) and
the price 7 / 30 calendar days later, for the "if you bought when they posted"
return. TW tickers map to Yahoo's ``<code>.TW`` (listed) / ``.TWO`` (OTC); US
tickers are used as-is.

The single network call lives in ``_fetch_closes`` so the window logic can be
unit-tested with a stubbed price series.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_BUFFER_BEFORE = 4   # days of slack before the post (skip weekends/holidays)
_BUFFER_AFTER = 8    # days past the 1-month window to ensure a trading day


def _yf_symbols(ticker: str, market: str) -> list[str]:
    if market == "US":
        return [ticker]
    if market == "TW":
        return [f"{ticker}.TW", f"{ticker}.TWO"]
    return [ticker]


def _fetch_closes(symbol: str, start: date, end: date) -> dict[date, float]:
    """Return {trading_date: close} for ``symbol`` in [start, end]. Network."""
    import yfinance as yf

    df = yf.Ticker(symbol).history(
        start=start.isoformat(), end=end.isoformat(), auto_adjust=False
    )
    if df is None or df.empty or "Close" not in df:
        return {}
    out: dict[date, float] = {}
    for ts, close in df["Close"].items():
        try:
            d = ts.date()
            out[d] = float(close)
        except (AttributeError, TypeError, ValueError):
            continue
    return out


def _closes_for(ticker: str, market: str, start: date, end: date) -> dict[date, float]:
    """Try each candidate Yahoo symbol; first non-empty wins."""
    for sym in _yf_symbols(ticker, market):
        try:
            closes = _fetch_closes(sym, start, end)
        except Exception:  # noqa: BLE001 — yfinance/network hiccup
            logger.warning("price_fetch_failed symbol=%s", sym)
            closes = {}
        if closes:
            return closes
    return {}


def compute_window(
    ticker: str,
    market: str,
    post_dt: datetime,
    today: date | None = None,
) -> dict:
    """Compute base / 7d / 1m prices + pct for one stock and post time.

    Returns a dict with base_date, base_price, price_7d, price_1m, pct_7d,
    pct_1m, status. 7d/1m stay None until that calendar window has fully
    elapsed (so the UI shows "追蹤中" rather than a misleading partial figure).
    """
    today = today or datetime.now(timezone.utc).date()
    post_date = post_dt.date()
    start = post_date - timedelta(days=_BUFFER_BEFORE)
    end = min(today, post_date + timedelta(days=30 + _BUFFER_AFTER)) + timedelta(days=1)

    closes = _closes_for(ticker, market, start, end)
    if not closes:
        return _result(None, None, None, None, "unavailable")

    dates = sorted(closes)
    base = next((d for d in dates if d >= post_date), None)
    if base is None:
        return _result(None, None, None, None, "unavailable")
    base_price = closes[base]

    def price_at(target: date) -> float | None:
        if target > today:
            return None  # window not elapsed yet
        cands = [d for d in dates if base < d <= target]
        return closes[cands[-1]] if cands else None

    p7 = price_at(post_date + timedelta(days=7))
    p1m = price_at(post_date + timedelta(days=30))

    if p7 is not None and p1m is not None:
        status = "done"
    elif p7 is not None:
        status = "partial"
    else:
        status = "pending"

    return _result(base, base_price, p7, p1m, status)


def _result(base, base_price, p7, p1m, status) -> dict:
    def pct(p):
        if p is None or not base_price:
            return None
        return (p - base_price) / base_price

    return {
        "base_date": base.isoformat() if base else None,
        "base_price": base_price,
        "price_7d": p7,
        "price_1m": p1m,
        "pct_7d": pct(p7),
        "pct_1m": pct(p1m),
        "status": status,
    }
