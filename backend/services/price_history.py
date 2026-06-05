"""Stock price windows via yfinance (no API token needed).

Given a post's date and a stock, compute the post-day close (base) and the
price 7 / 30 calendar days later. The window is **direction-neutral** — the
caller (frontend) interprets it as a gain or an avoided drop depending on
whether the post was a buy or a sell. TW tickers map to Yahoo's ``<code>.TW``
(listed) / ``.TWO`` (OTC); US tickers are used as-is.

The single network call lives in ``_fetch_closes`` so the window logic can be
unit-tested with a stubbed price series.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_BUFFER_BEFORE = 4   # days of slack before the post (skip weekends/holidays)

# Index tickers → their Yahoo symbol (大盤 tracked by points).
_INDEX_YF = {"TAIEX": "^TWII"}


def _yf_symbols(ticker: str, market: str) -> list[str]:
    if market == "INDEX":
        return [_INDEX_YF.get(ticker, ticker)]
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
            value = float(close)
            d = ts.date()
        except (AttributeError, TypeError, ValueError):
            continue
        if value != value or value <= 0:  # skip NaN / non-positive (incomplete bar)
            continue
        out[d] = value
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
    end = today + timedelta(days=1)  # always up to the latest trading day

    closes = _closes_for(ticker, market, start, end)
    if not closes:
        return _result(None, None, None, None, None, None, "unavailable")

    dates = sorted(closes)
    base = next((d for d in dates if d >= post_date), None)
    if base is None:
        return _result(None, None, None, None, None, None, "unavailable")
    base_price = closes[base]

    def price_at(target: date) -> float | None:
        if target > today:
            return None  # window not elapsed yet
        cands = [d for d in dates if base < d <= target]
        return closes[cands[-1]] if cands else None

    p7 = price_at(post_date + timedelta(days=7))
    p1m = price_at(post_date + timedelta(days=30))

    # "latest" = most recent close we have (current performance). Always
    # available once we have a base price.
    latest_d = dates[-1]
    p_latest = closes[latest_d]

    if p7 is not None and p1m is not None:
        status = "done"
    elif p7 is not None:
        status = "partial"
    else:
        status = "pending"

    return _result(base, base_price, p7, p1m, p_latest, latest_d, status)


def _result(base, base_price, p7, p1m, p_latest, latest_d, status) -> dict:
    def pct(p):
        if p is None or not base_price:
            return None
        return (p - base_price) / base_price

    return {
        "base_date": base.isoformat() if base else None,
        "base_price": base_price,
        "price_7d": p7,
        "price_1m": p1m,
        "price_latest": p_latest,
        "latest_date": latest_d.isoformat() if latest_d else None,
        "pct_7d": pct(p7),
        "pct_1m": pct(p1m),
        "pct_latest": pct(p_latest),
        "status": status,
    }
