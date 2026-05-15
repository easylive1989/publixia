"""成交量 fetchers — 台股成交金額（億元）。"""
import json
import sys
import os

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator

TWSE_FMTQIK_URL = "https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK"


def fetch_tw_volume():
    """台股每日成交金額（億元），來源 TWSE FMTQIK。"""
    try:
        r = requests.get(TWSE_FMTQIK_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        if not data:
            print("[tw_volume] empty response")
            return
        latest = data[-1]
        prev = data[-2] if len(data) >= 2 else latest
        value_yuan = int(latest["TradeValue"])
        prev_yuan = int(prev["TradeValue"])
        value_yi = round(value_yuan / 1e8, 2)  # 元 → 億元
        prev_yi = round(prev_yuan / 1e8, 2)
        change_pct = round((value_yi - prev_yi) / prev_yi * 100, 2) if prev_yi else 0.0
        save_indicator("tw_volume", value_yi, json.dumps({
            "change_pct": change_pct,
            "prev_value": prev_yi,
            "unit": "億元",
            "date": latest["Date"],
        }))
        print(f"[tw_volume] {latest['Date']} {value_yi} 億元 ({change_pct:+}%)")
    except Exception as e:
        print(f"[tw_volume] Error: {e}")
