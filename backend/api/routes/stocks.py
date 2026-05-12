"""Stock + watchlist routes."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from api._constants import RANGE_DELTAS
from api.dependencies import require_token, require_user
from api.schemas.stocks import AddStockRequest
from repositories.chip import get_chip_daily_range
from repositories.stocks import (
    add_watched_ticker, get_latest_stock, get_watched_tickers, remove_watched_ticker,
)


def _gate_or_404(user_id: int, ticker: str) -> None:
    """Raise 404 unless the ticker is in the user's personal watchlist."""
    ticker = ticker.upper()
    if ticker in get_watched_tickers(user_id):
        return
    raise HTTPException(
        status_code=404,
        detail="Ticker not in your watchlist. Add it via POST /api/stocks first.",
    )
from fetchers.yfinance_fetcher import fetch_all_stocks, fetch_stock_history
from fetchers.chip_stock import fetch_stock_chip, to_finmind_id as chip_to_finmind_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["stocks"], dependencies=[Depends(require_token)])


@router.get("/stocks")
def get_stocks(user: dict = Depends(require_user)):
    result = []
    for ticker in get_watched_tickers(user["id"]):
        row = get_latest_stock(ticker)
        if row:
            result.append({
                "ticker":     ticker,
                "name":       row["name"],
                "price":      row["price"],
                "change":     row["change"],
                "change_pct": row["change_pct"],
                "currency":   row["currency"],
                "timestamp":  row["timestamp"],
            })
        else:
            result.append({"ticker": ticker, "name": ticker, "price": None})
    return result


@router.post("/stocks")
def add_stock(req: AddStockRequest, user: dict = Depends(require_user)):
    add_watched_ticker(user["id"], req.ticker.upper())
    try:
        fetch_all_stocks()
    except Exception as e:
        logger.warning("add_stock_fetch_error error=%s", e)
    return {"ok": True}


@router.delete("/stocks/{ticker}")
def delete_stock(ticker: str, user: dict = Depends(require_user)):
    remove_watched_ticker(user["id"], ticker.upper())
    return {"ok": True}


@router.get("/stocks/{ticker}/brokers")
def stock_brokers(ticker: str, days: int = 20, top: int = 5,
                  user: dict = Depends(require_user)):
    _gate_or_404(user["id"], ticker)
    # 已停用：FinMind TaiwanStockTradingDailyReport 改為 Sponsor 限定 (見 README)。
    # 程式碼保留以便未來重啟功能。
    return {
        "ticker":      ticker.upper(),
        "days":        days,
        "as_of":       None,
        "ok":          False,
        "top_brokers": [],
    }


@router.get("/stocks/{ticker}/chip")
def stock_chip(ticker: str, days: int = 20,
               user: dict = Depends(require_user)):
    """個股籌碼:近 N 個交易日的三大法人淨買賣 + 融資融券餘額。

    Lazy fetch + DB cache。輸出每筆 row 含:
    foreign_net / trust_net / dealer_net(buy-sell)、margin_balance、short_balance。
    """
    ticker = ticker.upper()
    _gate_or_404(user["id"], ticker)
    if chip_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be 1..90")

    fetched = fetch_stock_chip(ticker)
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=int(days * 1.6) + 5)).isoformat()
    rows = get_chip_daily_range(ticker, since_date)

    if not rows:
        return {
            "ticker": ticker, "days": days, "as_of": None,
            "ok": fetched, "rows": [],
        }

    distinct_dates = sorted({r["date"] for r in rows})
    window_dates = distinct_dates[-days:]
    window_set = set(window_dates)

    def _net(b, s) -> float | None:
        if b is None and s is None:
            return None
        return (b or 0) - (s or 0)

    out_rows = []
    for r in rows:
        if r["date"] not in window_set:
            continue
        out_rows.append({
            "date":           r["date"],
            "foreign_net":    _net(r["foreign_buy"], r["foreign_sell"]),
            "trust_net":      _net(r["trust_buy"], r["trust_sell"]),
            "dealer_net":     _net(r["dealer_buy"], r["dealer_sell"]),
            "margin_balance": r["margin_balance"],
            "short_balance":  r["short_balance"],
        })

    return {
        "ticker": ticker, "days": days,
        "as_of": window_dates[-1] if window_dates else None,
        "ok": True, "rows": out_rows,
    }


@router.get("/stocks/{ticker}/history")
def stock_history(ticker: str, time_range: str = "3M",
                  user: dict = Depends(require_user)):
    _gate_or_404(user["id"], ticker)
    if time_range not in RANGE_DELTAS:
        raise HTTPException(status_code=400, detail="Unknown time_range")
    try:
        data = fetch_stock_history(ticker.upper(), time_range)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
    if data is None:
        raise HTTPException(status_code=404, detail="No history available")
    return data
