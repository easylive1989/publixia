"""台灣指數期貨 (TX) fetcher。

Source: FinMind TaiwanFuturesDaily,免費 dataset。每天每口合約一筆,
我們選每日成交量最大的一筆作為「近月連續合約」的代表寫入
futures_daily 表;同時把當日 close + 漲跌幅寫入 indicator_snapshots
讓 dashboard 卡片用既有的 history 機制讀取。

Lazy fetch + DB cache:首次拉 5 年,之後只補 delta。
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import (
    save_futures_daily_rows, get_latest_futures_date, get_futures_daily_range,
    save_indicator,
)
from core.settings import settings
from alerts import check_alerts

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = settings.finmind_token.get_secret_value().strip()

DATASET = "TaiwanFuturesDaily"
SYMBOL = "TX"          # 台指期 (大台)
INITIAL_LOOKBACK_DAYS = 365 * 5  # 首次抓 5 年


def _request(start_date: str, end_date: str) -> list[dict]:
    params = {
        "dataset":    DATASET,
        "data_id":    SYMBOL,
        "start_date": start_date,
        "end_date":   end_date,
    }
    headers = {}
    if FINMIND_TOKEN:
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"
    r = requests.get(FINMIND_URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"FinMind {DATASET} error: {payload.get('msg') or payload}")
    return payload.get("data") or []


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _is_day_session(row: dict) -> bool:
    """Filter to regular day-session rows (excludes after-hours)."""
    sess = row.get("trading_session")
    if sess is None:
        return True  # 舊資料無此欄
    return sess in ("position", "Position")


def parse_front_month(rows: list[dict]) -> list[dict]:
    """每日選成交量最大的合約 = 近月連續。

    FinMind 每筆有 contract_date(YYYYMM 月份合約)+ open/max/min/close/
    volume/settlement_price/open_interest/trading_session 等欄位。
    """
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        d = r.get("date")
        if not d or not _is_day_session(r):
            continue
        # 過濾掉零成交的列(可能是停盤合約)
        vol = _safe_float(r.get("volume"))
        if vol is None or vol <= 0:
            continue
        by_day[d].append(r)

    out: list[dict] = []
    for d, group in by_day.items():
        # 最大成交量者 = 近月主力
        pick = max(group, key=lambda r: _safe_float(r.get("volume")) or 0)
        out.append({
            "symbol":        SYMBOL,
            "date":          d,
            "contract_date": pick.get("contract_date"),
            "open":          _safe_float(pick.get("open")),
            "high":          _safe_float(pick.get("max")),
            "low":           _safe_float(pick.get("min")),
            "close":         _safe_float(pick.get("close")),
            "volume":        _safe_float(pick.get("volume")),
            "open_interest": _safe_float(pick.get("open_interest")),
            "settlement":    _safe_float(pick.get("settlement_price")),
        })
    out.sort(key=lambda r: r["date"])
    return out


def _save_indicator_snapshot(rows: list[dict]) -> None:
    """把每一筆 OHLCV 都寫成 indicator_snapshots(tw_futures),
    讓 dashboard 既有的 sparkline 直接用 /api/history 讀。"""
    prev_close = None
    for r in rows:
        close = r.get("close")
        if close is None:
            continue
        change_pct = 0.0
        if prev_close:
            change_pct = round((close - prev_close) / prev_close * 100, 2)
        save_indicator(
            "tw_futures",
            close,
            json.dumps({
                "change_pct": change_pct,
                "prev_close": round(prev_close, 2) if prev_close else round(close, 2),
                "volume":     r.get("volume"),
                "contract":   r.get("contract_date"),
            }),
            date=r["date"],
        )
        prev_close = close


def fetch_tw_futures(lookback_days: int | None = None) -> bool:
    """Lazy fetch + DB cache。失敗回 False(不擋住其他指標)。"""
    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_futures_date(SYMBOL)
    if latest:
        latest_date = datetime.strptime(latest, "%Y-%m-%d").date()
        if (today - latest_date).days <= 0:
            return True
        # 多回 7 天以容錯(連假回補)
        start = latest_date - timedelta(days=7)
    else:
        days = lookback_days or INITIAL_LOOKBACK_DAYS
        start = today - timedelta(days=days)
    start_date = start.strftime("%Y-%m-%d")
    if start_date > end_date:
        return True

    try:
        raw = _request(start_date, end_date)
    except Exception as e:
        print(f"[tw_futures] fetch error: {e}")
        return False

    parsed = parse_front_month(raw)
    if not parsed:
        return True
    save_futures_daily_rows(parsed)
    _save_indicator_snapshot(parsed)

    last_close = parsed[-1].get("close")
    if last_close is not None:
        check_alerts("indicator", "tw_futures", last_close)
    print(f"[tw_futures] {start_date}~{end_date}: {len(parsed)} day-rows")
    return True


# Expose for routes layer
def get_tw_futures_history(since_date: str) -> list[dict]:
    return get_futures_daily_range(SYMBOL, since_date)
