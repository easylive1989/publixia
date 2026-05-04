"""CNN Fear & Greed Index fetcher.

API: https://production.dataviz.cnn.io/index/fearandgreed/graphdata
回傳當日分數（0–100）及近一年歷史。
"""
import json
import requests
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator
from alerts import check_alerts

CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
    "Accept": "application/json",
}

RATING_ZH = {
    "extreme fear":  "極度恐懼",
    "fear":          "恐懼",
    "neutral":       "中立",
    "greed":         "貪婪",
    "extreme greed": "極度貪婪",
}


def _label(rating: str) -> str:
    return RATING_ZH.get(rating.lower(), rating)


def fetch_fear_greed():
    try:
        resp = requests.get(CNN_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("fear_and_greed", {})
        score = float(current.get("score", 0))
        rating = current.get("rating", "")

        score_rounded = round(score, 1)
        save_indicator("fear_greed", score_rounded, json.dumps({
            "label": _label(rating),
            "rating_en": rating,
        }))
        check_alerts("indicator", "fear_greed", score_rounded)
        print(f"[fear_greed] 分數={score} ({_label(rating)})")
    except Exception as e:
        print(f"[fear_greed] Error: {e}")
