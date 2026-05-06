"""台灣指數期貨 fetchers — TX (大台), MTX (小台), TMF (微台)。

Source: FinMind TaiwanFuturesDaily,免費 dataset。每天每口合約一筆,
每個 symbol 都選每日成交量最大的一筆作為「近月連續合約」寫入
futures_daily 表。

TX 額外把當日 close + 漲跌幅寫入 indicator_snapshots(讓 dashboard 卡
片用既有的 history 機制讀取),並會觸發 indicator alert。MTX/TMF 不
需要這個——它們只是給策略引擎讀的 OHLCV 來源。

每個 symbol 寫完當日 row 之後都會 call services.strategy_engine.
on_futures_data_written(symbol, last_date) 推進相關策略的 state
machine。

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
SYMBOL = "TX"          # 大台 — kept for back-compat with pre-P3 tests/imports.
INITIAL_LOOKBACK_DAYS = 365 * 5  # 首次抓 5 年


def _request(symbol: str = "TX",
             start_date: str | None = None,
             end_date: str | None = None) -> list[dict]:
    """FinMind TaiwanFuturesDaily query for one symbol + date range.

    `symbol` defaults to "TX" so legacy callers / mocks that pass only
    (start, end) still work — pre-P3 tests use ``patch(..., return_value=...)``
    which ignores arguments, but we keep the default for any positional
    invocation that survived.
    """
    params = {
        "dataset":    DATASET,
        "data_id":    symbol,
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
    sess = row.get("trading_session")
    if sess is None:
        return True
    return sess in ("position", "Position")


def parse_front_month(rows: list[dict], symbol: str = "TX") -> list[dict]:
    """每日選成交量最大的合約 = 近月連續。

    `symbol` defaults to "TX" so pre-P3 tests calling
    ``parse_front_month(SAMPLE_RAW)`` continue to work.
    """
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        d = r.get("date")
        if not d or not _is_day_session(r):
            continue
        vol = _safe_float(r.get("volume"))
        if vol is None or vol <= 0:
            continue
        by_day[d].append(r)

    out: list[dict] = []
    for d, group in by_day.items():
        pick = max(group, key=lambda r: _safe_float(r.get("volume")) or 0)
        out.append({
            "symbol":        symbol,
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
    """TX-only: feed dashboard's tw_futures sparkline."""
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


def _fetch_for_symbol(symbol: str, *, save_indicator_snapshot: bool,
                     lookback_days: int | None = None) -> bool:
    """Shared FinMind fetch + parse + persist + engine hook for any symbol."""
    today = datetime.now(timezone.utc).astimezone().date()
    end_date = today.strftime("%Y-%m-%d")

    latest = get_latest_futures_date(symbol)
    if latest:
        latest_date = datetime.strptime(latest, "%Y-%m-%d").date()
        if (today - latest_date).days <= 0:
            return True
        start = latest_date - timedelta(days=7)
    else:
        days = lookback_days or INITIAL_LOOKBACK_DAYS
        start = today - timedelta(days=days)
    start_date = start.strftime("%Y-%m-%d")
    if start_date > end_date:
        return True

    try:
        raw = _request(symbol, start_date, end_date)
    except Exception as e:
        print(f"[{symbol.lower()}] fetch error: {e}")
        return False

    parsed = parse_front_month(raw, symbol=symbol)
    if not parsed:
        return True
    save_futures_daily_rows(parsed)

    if save_indicator_snapshot:
        _save_indicator_snapshot(parsed)
        last_close = parsed[-1].get("close")
        if last_close is not None:
            check_alerts("indicator", "tw_futures", last_close)

    last_date = parsed[-1].get("date")
    if last_date:
        # Lazy import — services.strategy_engine pulls in repositories /
        # services_dsl which would be a startup-time circular if imported
        # at module top.
        from services.strategy_engine import on_futures_data_written
        on_futures_data_written(symbol, last_date)

    print(f"[{symbol.lower()}] {start_date}~{end_date}: {len(parsed)} day-rows")
    return True


# ── public entrypoints ──────────────────────────────────────────────

def fetch_tw_futures(lookback_days: int | None = None) -> bool:
    """大台 (TX) — also feeds the dashboard sparkline + alerts."""
    return _fetch_for_symbol("TX", save_indicator_snapshot=True,
                             lookback_days=lookback_days)


def fetch_tw_futures_mtx(lookback_days: int | None = None) -> bool:
    """小台 (MTX) — strategy engine only, no dashboard side effects."""
    return _fetch_for_symbol("MTX", save_indicator_snapshot=False,
                             lookback_days=lookback_days)


def fetch_tw_futures_tmf(lookback_days: int | None = None) -> bool:
    """微台 (TMF) — strategy engine only, no dashboard side effects."""
    return _fetch_for_symbol("TMF", save_indicator_snapshot=False,
                             lookback_days=lookback_days)


# Expose for routes layer (back-compat: TX-only history endpoint).
def get_tw_futures_history(since_date: str) -> list[dict]:
    return get_futures_daily_range("TX", since_date)
