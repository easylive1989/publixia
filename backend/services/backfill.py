"""一次性執行：補齊歷史資料到 SQLite DB。"""
import json
import logging
import re
import sys
import os
from datetime import datetime, timezone, timedelta

import yfinance as yf
import cloudscraper

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import init_db, get_connection, save_indicator

logger = logging.getLogger(__name__)


def _ts(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat()


def backfill_yfinance(ticker_symbol: str, indicator: str, extra_fn, period: str = "2y"):
    logger.info("backfill_yfinance_start indicator=%s ticker=%s", indicator, ticker_symbol)
    hist = yf.Ticker(ticker_symbol).history(period=period)
    if hist.empty:
        logger.warning("backfill_no_data indicator=%s ticker=%s", indicator, ticker_symbol)
        return
    inserted = 0
    with get_connection() as conn:
        for ts, row in hist.iterrows():
            price = float(row["Close"])
            dt = ts.to_pydatetime().replace(tzinfo=None)
            extra = extra_fn(price, hist, ts)
            conn.execute(
                "INSERT OR IGNORE INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
                (indicator, dt.isoformat(), price, json.dumps(extra)),
            )
            inserted += 1
    logger.info("backfill_inserted indicator=%s rows=%d", indicator, inserted)


def backfill_taiex():
    def extra(price, hist, ts):
        idx = hist.index.get_loc(ts)
        prev = float(hist.iloc[idx - 1]["Close"]) if idx > 0 else price
        pct = round((price - prev) / prev * 100, 2) if prev else 0
        return {"change_pct": pct, "prev_close": round(prev, 2)}
    backfill_yfinance("^TWII", "taiex", extra)


def backfill_fx():
    def extra(price, hist, ts):
        idx = hist.index.get_loc(ts)
        prev = float(hist.iloc[idx - 1]["Close"]) if idx > 0 else price
        pct = round((price - prev) / prev * 100, 4) if prev else 0
        return {"change_pct": pct, "prev_close": round(prev, 4)}
    backfill_yfinance("TWD=X", "fx", extra)


def backfill_tw_volume():
    """TWSE FMTQIK 提供近 18 天台股每日成交金額。"""
    import requests
    logger.info("backfill_tw_volume_start source=twse")
    r = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK", timeout=15)
    data = r.json()
    inserted = 0
    with get_connection() as conn:
        for i, row in enumerate(data):
            value_yi = round(int(row["TradeValue"]) / 1e8, 2)
            prev_yi = round(int(data[i - 1]["TradeValue"]) / 1e8, 2) if i > 0 else value_yi
            pct = round((value_yi - prev_yi) / prev_yi * 100, 2) if prev_yi else 0
            # Date 格式：1150428 → 民國 → 西元 2026-04-28
            d = row["Date"]
            year = int(d[:3]) + 1911
            dt = datetime(year, int(d[3:5]), int(d[5:7]))
            conn.execute(
                "INSERT OR IGNORE INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
                ("tw_volume", dt.isoformat(), value_yi,
                 json.dumps({"change_pct": pct, "prev_value": prev_yi, "unit": "億元", "date": d})),
            )
            inserted += 1
    logger.info("backfill_inserted indicator=%s rows=%d", "tw_volume", inserted)


def backfill_us_volume():
    """yfinance ^GSPC 提供 S&P 500 近 2 年成交量。"""
    import math
    import yfinance as yf
    logger.info("backfill_us_volume_start source=yfinance ticker=^GSPC")
    hist = yf.Ticker("^GSPC").history(period="2y")
    if hist.empty:
        logger.warning("backfill_no_data indicator=%s ticker=%s", "us_volume", "^GSPC")
        return
    valid = [(idx, float(v)) for idx, v in hist["Volume"].items()
             if not math.isnan(v) and v > 0]
    inserted = 0
    with get_connection() as conn:
        for i, (idx, vol) in enumerate(valid):
            value_yi = round(vol / 1e8, 2)
            prev_yi = round(valid[i - 1][1] / 1e8, 2) if i > 0 else value_yi
            pct = round((value_yi - prev_yi) / prev_yi * 100, 2) if prev_yi else 0
            dt = idx.to_pydatetime().replace(tzinfo=None)
            conn.execute(
                "INSERT OR IGNORE INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
                ("us_volume", dt.isoformat(), value_yi,
                 json.dumps({"change_pct": pct, "prev_value": prev_yi, "unit": "億股"})),
            )
            inserted += 1
    logger.info("backfill_inserted indicator=%s rows=%d", "us_volume", inserted)


def backfill_ndc():
    logger.info("backfill_ndc_start source=ndc_api")
    NDC_PAGE_URL = "https://index.ndc.gov.tw/n/zh_tw/data/eco"
    NDC_API_URL = "https://index.ndc.gov.tw/n/json/data/eco/indicators"
    LIGHT_NAMES = {1: "藍燈", 2: "黃藍燈", 3: "綠燈", 4: "黃紅燈", 5: "紅燈"}

    scraper = cloudscraper.create_scraper()
    page = scraper.get(NDC_PAGE_URL, timeout=20)
    match = re.search(r'csrf-token[^>]*content=["\']([^"\']+)', page.text)
    if not match:
        logger.warning("backfill_ndc_csrf_missing")
        return
    csrf = match.group(1)
    headers = {
        "X-CSRF-TOKEN": csrf,
        "Content-Type": "application/json",
        "Referer": NDC_PAGE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = scraper.post(NDC_API_URL, headers=headers, json={}, timeout=30)
    data = resp.json()
    line = data.get("line", {})
    score_series = line.get("12", {}).get("data", [])
    light_series = line.get("2", {}).get("data", [])

    # 建立 x→light_code 快查表
    light_map = {d["x"]: int(d["y"]) for d in light_series if d.get("y") is not None}

    # 只補近 5 年資料
    cutoff_x = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y%m")
    rows = [d for d in score_series if d.get("y") is not None and d.get("x", "") >= cutoff_x]

    inserted = 0
    with get_connection() as conn:
        for d in rows:
            x = d["x"]  # YYYYMM
            score = float(d["y"])
            year, month = int(x[:4]), int(x[4:])
            dt = datetime(year, month, 1)
            light_code = light_map.get(x, 0)
            light_name = LIGHT_NAMES.get(light_code, "未知")
            period = f"{x[:4]}/{x[4:]}"
            conn.execute(
                "INSERT OR IGNORE INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
                ("ndc", dt.isoformat(), score, json.dumps({
                    "light": light_name, "light_code": light_code, "period": period
                })),
            )
            inserted += 1
    logger.info("backfill_inserted indicator=%s rows=%d", "ndc", inserted)


def backfill_fear_greed():
    """從 CNN API 補近一年 Fear & Greed 歷史資料。"""
    logger.info("backfill_fear_greed_start source=cnn")
    from fetchers.fear_greed import CNN_URL, HEADERS, _label
    resp = __import__("requests").get(CNN_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    historical = data.get("fear_and_greed_historical", {}).get("data", [])
    if not historical:
        logger.warning("backfill_no_historical_data indicator=%s", "fear_greed")
        return
    inserted = 0
    with get_connection() as conn:
        for point in historical:
            ts_ms = point.get("x")
            score = point.get("y")
            rating = point.get("rating", "")
            if ts_ms is None or score is None:
                continue
            dt = datetime.fromtimestamp(ts_ms / 1000)
            conn.execute(
                "INSERT OR IGNORE INTO indicator_snapshots (indicator, timestamp, value, extra_json) VALUES (?,?,?,?)",
                ("fear_greed", dt.isoformat(), round(float(score), 1),
                 json.dumps({"label": _label(rating), "rating_en": rating})),
            )
            inserted += 1
    logger.info("backfill_inserted indicator=%s rows=%d", "fear_greed", inserted)


def backfill_chip_total(days: int = 365):
    """一次性從 FinMind 拉近 N 天的整體融資融券,寫入 indicator_snapshots。"""
    from datetime import timedelta
    from fetchers.chip_total import fetch_chip_total
    today = datetime.now()
    start = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    logger.info("backfill_chip_total_start range=%s_to_%s", start, end)
    fetch_chip_total(start_date=start, end_date=end)
    logger.info("backfill_section_done section=chip_total")


def main():
    import sys as _sys
    init_db()
    if len(_sys.argv) > 1 and _sys.argv[1] == "chip_total":
        backfill_chip_total(int(_sys.argv[2]) if len(_sys.argv) > 2 else 365)
    elif len(_sys.argv) > 1 and _sys.argv[1] == "fear_greed":
        backfill_fear_greed()
    elif len(_sys.argv) > 1 and _sys.argv[1] == "volume":
        backfill_tw_volume()
        backfill_us_volume()
    else:
        backfill_taiex()
        backfill_fx()
        backfill_ndc()
        backfill_fear_greed()
        backfill_tw_volume()
        backfill_us_volume()
        backfill_chip_total(365)
    logger.info("backfill_done")


if __name__ == "__main__":
    from core.logging import setup_logging
    setup_logging()
    main()
