"""個股基本面 fetcher,lazy fetch + DB cache。

從 FinMind 抓 6 個 dataset(全部免費 with data_id):
- TaiwanStockPER (每日 PER/PBR/殖利率) → stock_per_daily
- TaiwanStockMonthRevenue (每月營收) → stock_revenue_monthly
- TaiwanStockFinancialStatements (損益表,每季) → stock_financial_quarterly (report_type='income')
- TaiwanStockBalanceSheet (資產負債表,每季) → stock_financial_quarterly (report_type='balance')
- TaiwanStockCashFlowsStatement (現金流量表,每季) → stock_financial_quarterly (report_type='cash_flow')
- TaiwanStockDividend (股利) → stock_dividend_history

複用 chip_stock.py 模式:lazy fetch + DB cache,失敗 log + return False。
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import (
    save_per_daily_rows, get_latest_per_date,
    save_revenue_monthly_rows, get_latest_revenue_ym,
    save_financial_quarterly_rows, get_latest_financial_date,
    save_dividend_history_rows, get_latest_dividend_announce_date,
)
from core.settings import settings

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = settings.finmind_token.get_secret_value().strip()

# 對應 spec 範圍
DEFAULT_PER_LOOKBACK_DAYS = 1825      # 5 年
DEFAULT_REVENUE_LOOKBACK_MONTHS = 36  # 3 年
DEFAULT_FINANCIAL_LOOKBACK_QUARTERS = 12  # 3 年(12 季)
DEFAULT_DIVIDEND_LOOKBACK_YEARS = 10  # 10 年

# Phase 2 三表名 → FinMind dataset name
FINANCIAL_DATASET = {
    "income":    "TaiwanStockFinancialStatements",
    "balance":   "TaiwanStockBalanceSheet",
    "cash_flow": "TaiwanStockCashFlowsStatement",
}


def to_finmind_id(ticker: str) -> str | None:
    """把 watchlist ticker 轉成 FinMind 純數字代碼,非台股回 None。複用 broker.py 邏輯。"""
    t = (ticker or "").upper().strip()
    if t.endswith(".TW"):
        return t[:-3]
    if t.endswith(".TWO"):
        return t[:-4]
    if t.isdigit():
        return t
    return None


def _request(dataset: str, stock_id: str, start_date: str, end_date: str | None = None) -> list[dict]:
    params = {"dataset": dataset, "data_id": stock_id, "start_date": start_date}
    if end_date:
        params["end_date"] = end_date
    headers = {}
    if FINMIND_TOKEN:
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"
    r = requests.get(FINMIND_URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"FinMind {dataset} error: {payload.get('msg') or payload}")
    return payload.get("data") or []


# === Parsers (pure functions, easy to unit-test) ===

def parse_per_rows(rows: list[dict], ticker: str) -> list[dict]:
    """TaiwanStockPER → list of {ticker, date, per, pbr, dividend_yield}."""
    out: list[dict] = []
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        out.append({
            "ticker":         ticker,
            "date":           d,
            "per":            float(r["PER"]) if r.get("PER") is not None else None,
            "pbr":            float(r["PBR"]) if r.get("PBR") is not None else None,
            "dividend_yield": float(r["dividend_yield"]) if r.get("dividend_yield") is not None else None,
        })
    return out


def parse_revenue_rows(rows: list[dict], ticker: str) -> list[dict]:
    """TaiwanStockMonthRevenue → list of {ticker, year, month, revenue, announced_date}."""
    out: list[dict] = []
    for r in rows:
        y, m = r.get("revenue_year"), r.get("revenue_month")
        if y is None or m is None:
            continue
        out.append({
            "ticker":         ticker,
            "year":           int(y),
            "month":          int(m),
            "revenue":        float(r["revenue"]) if r.get("revenue") is not None else None,
            "announced_date": r.get("create_time") or None,
        })
    return out


def parse_financial_rows(rows: list[dict], ticker: str, report_type: str) -> list[dict]:
    """三表共用 long-format parser。

    rows 形如 {date, stock_id, type, value, origin_name},直接展開為 DB 列。
    """
    out: list[dict] = []
    for r in rows:
        d, t = r.get("date"), r.get("type")
        if not d or not t:
            continue
        out.append({
            "ticker":      ticker,
            "date":        d,
            "report_type": report_type,
            "type":        t,
            "value":       float(r["value"]) if r.get("value") is not None else None,
        })
    return out


def parse_dividend_rows(rows: list[dict], ticker: str) -> list[dict]:
    """TaiwanStockDividend → list of {ticker, year, cash_dividend, stock_dividend,
    cash_ex_date, cash_payment_date, announcement_date}."""
    out: list[dict] = []
    for r in rows:
        y = r.get("year")
        if not y:
            continue
        out.append({
            "ticker":            ticker,
            "year":              y,
            "cash_dividend":     float(r["CashEarningsDistribution"])  if r.get("CashEarningsDistribution")  is not None else None,
            "stock_dividend":    float(r["StockEarningsDistribution"]) if r.get("StockEarningsDistribution") is not None else None,
            "cash_ex_date":      r.get("CashExDividendTradingDate") or None,
            "cash_payment_date": r.get("CashDividendPaymentDate") or None,
            "announcement_date": r.get("AnnouncementDate") or None,
        })
    return out


# === Fetchers (lazy fetch + DB cache) ===

def fetch_stock_per(ticker: str, lookback_days: int = DEFAULT_PER_LOOKBACK_DAYS) -> bool:
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_per_date(ticker)
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
        raw = _request("TaiwanStockPER", stock_id, start_date, end_date)
    except Exception as e:
        print(f"[fundamentals] {ticker} PER fetch error: {e}")
        return False

    rows = parse_per_rows(raw, ticker)
    save_per_daily_rows(rows)
    # Phase 4 alert 觸發:只在「最新一天有寫入」時針對 3 個估值指標檢查
    today_str = today.strftime("%Y-%m-%d")
    max_date = max((r["date"] for r in rows), default=None)
    if max_date == today_str:
        from alerts import check_alerts
        for key in ("per", "pbr", "dividend_yield"):
            check_alerts("stock_indicator", ticker, indicator_key=key)
    print(f"[fundamentals] {ticker} PER {start_date}~{end_date}: {len(rows)} rows")
    return True


def fetch_stock_revenue(ticker: str, months: int = DEFAULT_REVENUE_LOOKBACK_MONTHS) -> bool:
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    latest_ym = get_latest_revenue_ym(ticker)
    if latest_ym:
        y, m = latest_ym
        start = datetime(y, m, 1) + timedelta(days=32)
        start = start.replace(day=1)
        if start.date() > today:
            return True
    else:
        start = today.replace(day=1) - timedelta(days=months * 31)
        start = start.replace(day=1)
    start_date = start.strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    try:
        raw = _request("TaiwanStockMonthRevenue", stock_id, start_date, end_date)
    except Exception as e:
        print(f"[fundamentals] {ticker} revenue fetch error: {e}")
        return False

    rows = parse_revenue_rows(raw, ticker)
    save_revenue_monthly_rows(rows)

    # Phase 4 follow-up alert 觸發:只在「實際拉到新月」時針對 revenue 指標檢查。
    # latest_ym 是 fetch 開始前的最新月(已在函式上方算出);post-fetch 比對。
    new_max_ym = max(((r["year"], r["month"]) for r in rows), default=None)
    if new_max_ym and (latest_ym is None or new_max_ym > latest_ym):
        from alerts import check_alerts
        check_alerts("stock_indicator", ticker, indicator_key="revenue")

    print(f"[fundamentals] {ticker} revenue {start_date}~{end_date}: {len(rows)} rows")
    return True


def fetch_stock_financial(ticker: str, report_type: str,
                          quarters: int = DEFAULT_FINANCIAL_LOOKBACK_QUARTERS) -> bool:
    """fetch 一個 statement (income/balance/cash_flow) 的資料。"""
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False
    dataset = FINANCIAL_DATASET.get(report_type)
    if dataset is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_financial_date(ticker, report_type)
    if latest:
        latest_date = datetime.strptime(latest, "%Y-%m-%d").date()
        # TWSE 季報申報期限約為季結束後 45 天;留 5 天 buffer。
        if (today - latest_date).days < 45:
            return True
        start = latest_date + timedelta(days=1)
    else:
        start = today - timedelta(days=quarters * 100)
    start_date = start.strftime("%Y-%m-%d")
    if start_date > end_date:
        return True

    try:
        raw = _request(dataset, stock_id, start_date, end_date)
    except Exception as e:
        print(f"[fundamentals] {ticker} financial({report_type}) fetch error: {e}")
        return False

    rows = parse_financial_rows(raw, ticker, report_type)
    save_financial_quarterly_rows(rows)

    # Phase 4 alert 觸發:只在拉到新季時針對對應 quarterly indicator 檢查
    new_max_date = max((r["date"] for r in rows), default=None)
    if new_max_date and (latest is None or new_max_date > latest):
        from alerts import check_alerts
        triggered_keys: list[str] = []
        if report_type == "income":
            triggered_keys = ["q_eps", "q_revenue", "q_operating_income", "q_net_income"]
        elif report_type == "cash_flow":
            triggered_keys = ["q_operating_cf"]
        # balance 不觸發(範圍外)
        for key in triggered_keys:
            check_alerts("stock_indicator", ticker, indicator_key=key)

    print(f"[fundamentals] {ticker} {report_type} {start_date}~{end_date}: {len(rows)} rows")
    return True


def fetch_stock_dividend(ticker: str, years: int = DEFAULT_DIVIDEND_LOOKBACK_YEARS) -> bool:
    stock_id = to_finmind_id(ticker)
    if stock_id is None:
        return False

    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest_announce = get_latest_dividend_announce_date(ticker)
    if latest_announce:
        latest_date = datetime.strptime(latest_announce, "%Y-%m-%d").date()
        start = latest_date + timedelta(days=1)
        if (today - latest_date).days < 30:
            return True
    else:
        start = today - timedelta(days=years * 366)

    from db import get_dividend_history
    pre_dividend_history = get_dividend_history(ticker)
    start_date = start.strftime("%Y-%m-%d")
    if start_date > end_date:
        return True

    try:
        raw = _request("TaiwanStockDividend", stock_id, start_date, end_date)
    except Exception as e:
        print(f"[fundamentals] {ticker} dividend fetch error: {e}")
        return False

    rows = parse_dividend_rows(raw, ticker)
    save_dividend_history_rows(rows)

    # Phase 4 alert 觸發:只在拉到新西元年才觸發 yearly indicator
    import re
    def _max_ce_year(items):
        years = []
        for r in items:
            m = re.match(r"^(\d{2,3})年", r.get("year") or "")
            if m:
                years.append(int(m.group(1)) + 1911)
        return max(years, default=None)

    pre_year = _max_ce_year(pre_dividend_history)
    new_year = _max_ce_year(rows)
    if new_year and (pre_year is None or new_year > pre_year):
        from alerts import check_alerts
        for key in ("y_cash_dividend", "y_stock_dividend"):
            check_alerts("stock_indicator", ticker, indicator_key=key)

    print(f"[fundamentals] {ticker} dividend {start_date}~{end_date}: {len(rows)} rows")
    return True


def fetch_watchlist_stock_daily() -> None:
    """Daily cron entry:對 watchlist 中所有台股 ticker 拉 chip_stock + PER。

    Lazy 路徑保留(個股頁打開時也拉);此函式確保 watchlist 上有警示的
    ticker 每天有最新資料,警示能可靠觸發。Watchlist 為空時 early return。
    """
    from db import get_watched_tickers
    from fetchers.chip_stock import fetch_stock_chip

    tickers = get_watched_tickers()
    tw_tickers = [t for t in tickers if to_finmind_id(t) is not None]
    if not tw_tickers:
        print("[watchlist_chip_per] watchlist 中無台股 ticker,skip")
        return

    print(f"[watchlist_chip_per] 拉 {len(tw_tickers)} 檔台股 chip + PER")
    for ticker in tw_tickers:
        try:
            fetch_stock_chip(ticker)
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} chip error: {e}")
        try:
            fetch_stock_per(ticker)
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} per error: {e}")
        try:
            fetch_stock_revenue(ticker)
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} revenue error: {e}")
        try:
            fetch_stock_financial(ticker, "income")
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} income error: {e}")
        try:
            fetch_stock_financial(ticker, "cash_flow")
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} cash_flow error: {e}")
        try:
            fetch_stock_dividend(ticker)
        except Exception as e:
            print(f"[watchlist_chip_per] {ticker} dividend error: {e}")
