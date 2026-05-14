"""Market-wide yfinance fetchers.

Only TAIEX (^TWII) and TWD/USD FX are kept — individual-stock fetchers
were removed when the dashboard dropped the stock-detail surface.
"""
import json
import math
import os
import sys

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator


def _is_valid(v) -> bool:
    return v is not None and not math.isnan(v)


def _fetch_price(ticker_obj) -> dict | None:
    """Latest close + change_pct + trading-day date for a yfinance Ticker.

    Walks back from the most recent row to find the last valid Close,
    so holiday / suspended-trading days don't produce phantom snapshots.
    """
    hist = ticker_obj.history(period="10d")
    if hist.empty:
        return None
    closes = [float(c) for c in hist["Close"].tolist()]
    valid_idx = [i for i, c in enumerate(closes) if _is_valid(c)]
    if not valid_idx:
        return None
    last_i = valid_idx[-1]
    price = closes[last_i]
    prev_close = closes[valid_idx[-2]] if len(valid_idx) >= 2 else price
    trade_date = hist.index[last_i].strftime("%Y-%m-%d")
    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    return {
        "price":      price,
        "change":     change,
        "change_pct": change_pct,
        "prev_close": prev_close,
        "date":       trade_date,
    }


def fetch_taiex():
    """Fetch Taiwan stock exchange index (^TWII)."""
    data = _fetch_price(yf.Ticker("^TWII"))
    if not data:
        return
    save_indicator(
        "taiex",
        data["price"],
        json.dumps({
            "change_pct": data["change_pct"],
            "prev_close": round(data["prev_close"], 2),
        }),
        date=data["date"],
    )


def fetch_fx():
    """Fetch TWD/USD exchange rate."""
    data = _fetch_price(yf.Ticker("TWD=X"))
    if not data:
        return
    fx_value = round(data["price"], 4)
    save_indicator(
        "fx",
        fx_value,
        json.dumps({
            "change_pct": data["change_pct"],
            "prev_close": round(data["prev_close"], 4),
        }),
        date=data["date"],
    )
