import json
import math
import yfinance as yf
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator, save_stock_snapshot, get_watched_tickers
from alerts import check_alerts


# yfinance period strings, with extra warm-up so MA60/MACD have values at the
# beginning of the visible window. The second value is how many trading days
# the frontend asked for; we slice the result to that length.
HISTORY_PERIODS: dict[str, tuple[str, int]] = {
    "1M": ("6mo", 22),
    "3M": ("9mo", 66),
    "6M": ("1y", 132),
    "1Y": ("2y", 252),
    "3Y": ("5y", 756),
}


def _is_valid(v) -> bool:
    return v is not None and not math.isnan(v)


def _fetch_price(ticker_obj) -> dict | None:
    """Fetch price data for a Ticker instance.

    yfinance 對某些台股盤前可能回傳 NaN，所以從最新往前找第一筆有效的 Close。
    `date` 是該 close 對應的交易日 (YYYY-MM-DD),從 yfinance 的 index 取得 —
    遇到假日/週末時不會等於今天,可避免在非交易日 upsert 出錯誤的 date。
    """
    # 拉長一點區間以便處理連假/停牌
    hist = ticker_obj.history(period="10d")
    if hist.empty:
        return None
    closes = [float(c) for c in hist["Close"].tolist()]
    # 找最後一筆有效 close,連同其對應的 index date 一起取出
    valid_idx = [i for i, c in enumerate(closes) if _is_valid(c)]
    if not valid_idx:
        return None
    last_i = valid_idx[-1]
    price = closes[last_i]
    prev_close = closes[valid_idx[-2]] if len(valid_idx) >= 2 else price
    trade_date = hist.index[last_i].strftime("%Y-%m-%d")
    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    currency = ""
    try:
        currency = ticker_obj.history_metadata.get("currency", "")
    except Exception:
        pass
    return {
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": round(change_pct, 2),
        "currency": currency,
        "date": trade_date,
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
    check_alerts("indicator", "taiex", data["price"])


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
    check_alerts("indicator", "fx", fx_value)


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _series_to_list(series) -> list[float | None]:
    return [_safe_float(v) for v in series.tolist()]


def _compute_indicators(close) -> dict:
    """Compute MA5/MA20/MA60, RSI14 and MACD(12,26,9) from a Close series."""
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi14 = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal

    return {
        "ma5": _series_to_list(ma5),
        "ma20": _series_to_list(ma20),
        "ma60": _series_to_list(ma60),
        "rsi14": _series_to_list(rsi14),
        "macd": _series_to_list(macd),
        "macd_signal": _series_to_list(macd_signal),
        "macd_histogram": _series_to_list(macd_hist),
    }


def fetch_stock_history(ticker: str, time_range: str = "3M") -> dict | None:
    """Fetch OHLCV history for a ticker plus computed technical indicators.

    Returns None if yfinance has no data. The response always exposes the same
    number of rows in `dates`, `candles` and each indicator series so the
    frontend can index them directly.
    """
    period, tail = HISTORY_PERIODS.get(time_range, HISTORY_PERIODS["3M"])
    stock = yf.Ticker(ticker)
    hist = stock.history(period=period, auto_adjust=False)
    if hist.empty:
        return None

    indicators = _compute_indicators(hist["Close"])

    name = ticker
    currency = ""
    try:
        currency = stock.history_metadata.get("currency", "") or ""
    except Exception:
        pass
    try:
        info = stock.info
        name = info.get("shortName") or info.get("longName") or ticker
    except Exception:
        pass

    candles = []
    dates = []
    for idx, row in hist.iterrows():
        dates.append(idx.strftime("%Y-%m-%d"))
        candles.append({
            "open":   _safe_float(row.get("Open")),
            "high":   _safe_float(row.get("High")),
            "low":    _safe_float(row.get("Low")),
            "close":  _safe_float(row.get("Close")),
            "volume": _safe_float(row.get("Volume")),
        })

    if tail < len(dates):
        start = len(dates) - tail
        dates = dates[start:]
        candles = candles[start:]
        indicators = {k: v[start:] for k, v in indicators.items()}

    return {
        "ticker":     ticker,
        "name":       name,
        "currency":   currency,
        "time_range": time_range,
        "dates":      dates,
        "candles":    candles,
        "indicators": indicators,
    }


def _is_tw_ticker(ticker: str) -> bool:
    """台股 ticker 在 yfinance 的慣例:`NNNN.TW` / `NNNN.TWO`。"""
    upper = ticker.upper()
    return upper.endswith(".TW") or upper.endswith(".TWO")


def _fetch_stocks(tickers: list[str]):
    """Fetch the given tickers, save one snapshot per (ticker, trade_date)."""
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            data = _fetch_price(stock)
            if not data:
                continue
            name = ticker
            try:
                info = stock.info
                name = info.get("shortName") or info.get("longName") or ticker
            except Exception:
                pass
            price = round(data["price"], 4)
            save_stock_snapshot(
                ticker,
                price,
                round(data["change"], 4),
                data["change_pct"],
                data["currency"],
                name,
                date=data["date"],
            )
            check_alerts("stock", ticker, price, display_name=name)
        except Exception as e:
            print(f"[yfinance] Error fetching {ticker}: {e}")


def fetch_tw_stocks():
    """Fetch all watched Taiwan-listed stocks (run after TWSE close, ~14:00 TST)."""
    tickers = [t for t in get_watched_tickers() if _is_tw_ticker(t)]
    _fetch_stocks(tickers)


def fetch_us_stocks():
    """Fetch all watched US-listed stocks (run after US close, ~06:00 TST)."""
    tickers = [t for t in get_watched_tickers() if not _is_tw_ticker(t)]
    _fetch_stocks(tickers)


def fetch_all_stocks():
    """Backwards-compatible wrapper — fetch every watched stock regardless of market."""
    _fetch_stocks(get_watched_tickers())
