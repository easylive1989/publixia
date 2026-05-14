"""台灣指數期貨詳細頁 API。

`/api/futures/tw/history?time_range=...` 回傳 OHLCV + 計算 MA / RSI / MACD。
資料來源:futures_daily 表(由 fetcher 從 FinMind lazy-fill)。
"""
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, HTTPException

from fetchers.futures import fetch_tw_futures, get_tw_futures_history, SYMBOL
from services.price_indicators import compute_indicators

router = APIRouter(prefix="/api", tags=["futures"])


# 期貨歷史窗口比一般指標長,且後端已快取多年資料
RANGE_LOOKBACK_DAYS: dict[str, int] = {
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
    "3Y": 365 * 3,
    "5Y": 365 * 5,
}


@router.get("/futures/tw/history")
def tw_futures_history(time_range: str = "3M"):
    if time_range not in RANGE_LOOKBACK_DAYS:
        raise HTTPException(status_code=400, detail="Unknown time_range")
    # 觸發一次 lazy fetch(成功為 cache hit / fail silent 不擋頁面)
    try:
        fetch_tw_futures()
    except Exception as e:
        # repository 仍可能有舊資料可回
        print(f"[futures-route] lazy fetch error: {e}")

    # 多抓 60 天作為 MA60/MACD warm-up,顯示時再 trim 回視窗
    today = datetime.now(timezone.utc).astimezone().date()
    days = RANGE_LOOKBACK_DAYS[time_range]
    warmup_days = days + 90
    since = (today - timedelta(days=warmup_days)).strftime("%Y-%m-%d")
    rows = get_tw_futures_history(since)
    if not rows:
        raise HTTPException(status_code=404, detail="No futures history available")

    closes = pd.Series([r["close"] for r in rows], dtype="float64")
    indicators = compute_indicators(closes)

    # trim 回想要的視窗(以日期切)
    cutoff = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    keep_idx = [i for i, r in enumerate(rows) if r["date"] >= cutoff]
    if not keep_idx:
        keep_idx = list(range(len(rows)))
    start = keep_idx[0]

    dates = [r["date"] for r in rows[start:]]
    candles = [
        {
            "open":   r["open"],
            "high":   r["high"],
            "low":    r["low"],
            "close":  r["close"],
            "volume": r["volume"],
        }
        for r in rows[start:]
    ]
    indicators_out = {k: v[start:] for k, v in indicators.items()}

    return {
        "symbol":     SYMBOL,
        "name":       "台指期 (TX)",
        "currency":   "TWD",
        "time_range": time_range,
        "dates":      dates,
        "candles":    candles,
        "indicators": indicators_out,
    }
