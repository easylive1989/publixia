"""個股籌碼 fetcher,lazy fetch + DB cache。

複用 broker.py 同模式:
- 從 watchlist ticker 解析 FinMind data_id(去 .TW / .TWO 後綴)
- 從 DB 取 latest cached date,僅補 delta 區間
- 預設首次拉 60 個交易日(用日曆日 90 天概抓涵蓋週末假日)

寫入新表 stock_chip_daily(ticker, date, foreign_buy, foreign_sell,
trust_buy, trust_sell, dealer_buy, dealer_sell, margin_balance,
short_balance)。API 層計算 *_net = buy - sell。
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_chip_daily_rows, get_latest_chip_date
from core.settings import settings

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = settings.finmind_token.get_secret_value().strip()

# 預設首次拉 90 個日曆天 ≒ 60 個交易日(涵蓋週末假日)
DEFAULT_LOOKBACK_DAYS = 90


def to_finmind_id(ticker: str) -> str | None:
    """Reuse 同 broker.py 邏輯:把 watchlist ticker 轉成 FinMind 純數字代碼。"""
    t = (ticker or "").upper().strip()
    if t.endswith(".TW"):
        return t[:-3]
    if t.endswith(".TWO"):
        return t[:-4]
    if t.isdigit():
        return t
    return None


def _request(dataset: str, stock_id: str, start_date: str, end_date: str) -> list[dict]:
    params = {
        "dataset":    dataset,
        "data_id":    stock_id,
        "start_date": start_date,
        "end_date":   end_date,
    }
    headers = {}
    if FINMIND_TOKEN:
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"
    r = requests.get(FINMIND_URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"FinMind {dataset} error: {payload.get('msg') or payload}")
    return payload.get("data") or []


def parse_stock_inst(rows: list[dict], ticker: str) -> list[dict]:
    """Long-format 個股三大法人 → per-day record。"""
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        d, n = r.get("date"), r.get("name")
        if not d or not n:
            continue
        by_day[d][n] = r

    def _bs(rec: dict | None) -> tuple[float, float]:
        if not rec:
            return 0, 0
        return float(rec.get("buy", 0) or 0), float(rec.get("sell", 0) or 0)

    out: list[dict] = []
    for d, names in by_day.items():
        f_b, f_s = _bs(names.get("Foreign_Investor"))
        fd_b, fd_s = _bs(names.get("Foreign_Dealer_Self"))
        t_b, t_s = _bs(names.get("Investment_Trust"))
        ds_b, ds_s = _bs(names.get("Dealer_self"))
        dh_b, dh_s = _bs(names.get("Dealer_Hedging"))
        out.append({
            "ticker": ticker,
            "date":   d,
            "foreign_buy":  f_b + fd_b,
            "foreign_sell": f_s + fd_s,
            "trust_buy":    t_b,
            "trust_sell":   t_s,
            "dealer_buy":   ds_b + dh_b,
            "dealer_sell":  ds_s + dh_s,
            "margin_balance": None,
            "short_balance":  None,
        })
    return out


def parse_stock_margin(rows: list[dict], ticker: str) -> list[dict]:
    """Wide-format 個股融資融券 → per-day record(只取 *TodayBalance 欄)。"""
    out: list[dict] = []
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        out.append({
            "ticker": ticker,
            "date":   d,
            "foreign_buy":  None,
            "foreign_sell": None,
            "trust_buy":    None,
            "trust_sell":   None,
            "dealer_buy":   None,
            "dealer_sell":  None,
            "margin_balance": float(r["MarginPurchaseTodayBalance"]) if r.get("MarginPurchaseTodayBalance") is not None else None,
            "short_balance":  float(r["ShortSaleTodayBalance"])      if r.get("ShortSaleTodayBalance")      is not None else None,
        })
    return out


def _merge(rows_a: list[dict], rows_b: list[dict]) -> list[dict]:
    """Merge two per-day records lists by (ticker, date). 後者覆蓋前者非空欄位。"""
    by_key: dict[tuple[str, str], dict] = {}
    for r in rows_a + rows_b:
        k = (r["ticker"], r["date"])
        existing = by_key.get(k, {})
        merged = {**existing, **{field: v for field, v in r.items() if v is not None}}
        # 確保 schema 完整
        for f in ("foreign_buy", "foreign_sell", "trust_buy", "trust_sell",
                  "dealer_buy", "dealer_sell", "margin_balance", "short_balance"):
            merged.setdefault(f, None)
        merged["ticker"] = r["ticker"]
        merged["date"]   = r["date"]
        by_key[k] = merged
    return sorted(by_key.values(), key=lambda x: x["date"])


def fetch_stock_chip(ticker: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> bool:
    """Lazy fetch + DB cache,失敗回 False(不擋住其他指標)。"""
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_chip_date(ticker)
    if latest:
        latest_date = datetime.strptime(latest, "%Y-%m-%d").date()
        if (today - latest_date).days <= 0:
            return True
        start = latest_date + timedelta(days=1)
    else:
        start = today - timedelta(days=lookback_days)
    start_date = start.strftime("%Y-%m-%d")
    if start_date > end_date:
        return True

    try:
        inst_raw = _request("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date, end_date)
        margin_raw = _request("TaiwanStockMarginPurchaseShortSale", stock_id, start_date, end_date)
    except Exception as e:
        print(f"[chip_stock] {ticker} fetch error: {e}")
        return False

    inst_rows   = parse_stock_inst(inst_raw, ticker)
    margin_rows = parse_stock_margin(margin_raw, ticker)
    merged = _merge(inst_rows, margin_rows)
    if not merged:
        return True
    save_chip_daily_rows(merged)
    # Phase 4 alert 觸發:只在「最新一天有寫入」時針對 5 個籌碼指標檢查
    today_str = today.strftime("%Y-%m-%d")
    max_date = max((r["date"] for r in merged), default=None)
    if max_date == today_str:
        from alerts import check_alerts
        for key in ("foreign_net", "trust_net", "dealer_net",
                    "margin_balance", "short_balance"):
            check_alerts("stock_indicator", ticker, indicator_key=key)
    print(f"[chip_stock] {ticker} {start_date}~{end_date}: {len(merged)} chip-day rows")
    return True
