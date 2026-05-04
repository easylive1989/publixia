"""券商分點 fetcher — 從 FinMind 取得個股每日券商買賣資料。

FinMind dataset: TaiwanStockTradingDailyReport
每筆資料是「某天、某券商、某成交價」的買進與賣出張數，
我們在這層 aggregate 成「每天、每券商」的總買進量、總賣出量、加權買進金額、
加權賣出金額，再寫入 DB。前五大券商買超、持續買入天數、平均買進價的計算
留給 API 層。
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_broker_daily_rows, get_latest_broker_date
from core.settings import settings

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = settings.finmind_token.get_secret_value().strip()
DATASET = "TaiwanStockTradingDailyReport"

# 一次 fetch 抓多少天，足夠涵蓋 20 個交易日 + 週末/假日
DEFAULT_LOOKBACK_DAYS = 35


def to_finmind_id(ticker: str) -> str | None:
    """將 watchlist ticker 轉成 FinMind 用的純數字代碼，非台股回傳 None。"""
    t = (ticker or "").upper().strip()
    if t.endswith(".TW"):
        return t[:-3]
    if t.endswith(".TWO"):
        return t[:-4]
    if t.isdigit():
        return t
    return None


def _aggregate(raw_rows: list[dict], ticker: str) -> list[dict]:
    """將 FinMind 的 row-per-price-level 聚合成 row-per-broker-per-day。"""
    bucket: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "buy_volume": 0.0,
        "sell_volume": 0.0,
        "buy_amount": 0.0,
        "sell_amount": 0.0,
        "securities_trader": "",
    })
    for row in raw_rows:
        date = row.get("date")
        broker_id = row.get("securities_trader_id")
        if not date or not broker_id:
            continue
        try:
            price = float(row.get("price") or 0)
            buy = float(row.get("buy") or 0)
            sell = float(row.get("sell") or 0)
        except (TypeError, ValueError):
            continue
        agg = bucket[(date, broker_id)]
        agg["buy_volume"] += buy
        agg["sell_volume"] += sell
        agg["buy_amount"] += buy * price
        agg["sell_amount"] += sell * price
        if not agg["securities_trader"]:
            agg["securities_trader"] = row.get("securities_trader") or ""

    return [
        {
            "ticker": ticker,
            "date": date,
            "securities_trader_id": broker_id,
            "securities_trader": agg["securities_trader"],
            "buy_volume": agg["buy_volume"],
            "sell_volume": agg["sell_volume"],
            "buy_amount": agg["buy_amount"],
            "sell_amount": agg["sell_amount"],
        }
        for (date, broker_id), agg in bucket.items()
    ]


def _request_finmind(stock_id: str, start_date: str, end_date: str) -> list[dict]:
    params = {
        "dataset": DATASET,
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    if FINMIND_TOKEN:
        params["token"] = FINMIND_TOKEN
    r = requests.get(FINMIND_URL, params=params, timeout=20)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != 200 and payload.get("status") is not None:
        msg = payload.get("msg") or payload.get("message") or "unknown"
        raise RuntimeError(f"FinMind error: {msg}")
    return payload.get("data") or []


def fetch_broker_daily(ticker: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> bool:
    """Fetch & cache broker daily data for a single TW ticker.

    Returns True on success (data fetched or already up to date), False otherwise.
    Skips network call if today's data already in DB.
    """
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_broker_date(ticker)
    if latest:
        latest_date = datetime.strptime(latest, "%Y-%m-%d").date()
        # 已是最新 (>= 今天 or 假日) 就略過
        if (today - latest_date).days <= 0:
            return True
        # 從上次資料隔天開始抓，避免重抓
        start = latest_date + timedelta(days=1)
    else:
        start = today - timedelta(days=lookback_days)
    start_date = start.strftime("%Y-%m-%d")
    if start_date > end_date:
        return True

    try:
        raw = _request_finmind(stock_id, start_date, end_date)
    except Exception as e:
        print(f"[broker] {ticker} fetch error: {e}")
        return False

    if not raw:
        return True

    rows = _aggregate(raw, ticker)
    save_broker_daily_rows(rows)
    print(f"[broker] {ticker} {start_date}~{end_date}: {len(rows)} broker-day rows")
    return True
