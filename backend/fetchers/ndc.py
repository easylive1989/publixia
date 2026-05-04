import json
import re
import sys
import os

import cloudscraper

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator
from alerts import check_alerts

NDC_PAGE_URL = "https://index.ndc.gov.tw/n/zh_tw/data/eco"
NDC_API_URL = "https://index.ndc.gov.tw/n/json/data/eco/indicators"

# line['12'] = SR0005 景氣對策信號（分）
# line['2']  = SR0030 景氣對策信號（燈號代碼 1-5）
SCORE_LINE_KEY = "12"
LIGHT_LINE_KEY = "2"
LIGHT_NAMES = {1: "藍燈", 2: "黃藍燈", 3: "綠燈", 4: "黃紅燈", 5: "紅燈"}


def fetch_ndc():
    try:
        scraper = cloudscraper.create_scraper()

        # 先取 CSRF token
        page = scraper.get(NDC_PAGE_URL, timeout=20)
        match = re.search(r'csrf-token[^>]*content=["\']([^"\']+)', page.text)
        if not match:
            print("[ndc] Cannot find CSRF token")
            return
        csrf = match.group(1)

        headers = {
            "X-CSRF-TOKEN": csrf,
            "Content-Type": "application/json",
            "Referer": NDC_PAGE_URL,
            "X-Requested-With": "XMLHttpRequest",
        }
        resp = scraper.post(NDC_API_URL, headers=headers, json={}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        line = data.get("line", {})
        score_series = line.get(SCORE_LINE_KEY, {}).get("data", [])
        light_series = line.get(LIGHT_LINE_KEY, {}).get("data", [])

        latest_score = next((d for d in reversed(score_series) if d.get("y") is not None), None)
        latest_light = next((d for d in reversed(light_series) if d.get("y") is not None), None)

        if not latest_score:
            print("[ndc] No score data found")
            return

        score = int(latest_score["y"])
        light_code = int(latest_light["y"]) if latest_light else 0
        light_name = LIGHT_NAMES.get(light_code, "未知")
        period = latest_score.get("x", "")
        # x 格式為 YYYYMM，轉換成 YYYY/MM
        if len(period) == 6:
            period = f"{period[:4]}/{period[4:]}"

        save_indicator("ndc", float(score), json.dumps({
            "light": light_name,
            "light_code": light_code,
            "period": period,
        }))
        check_alerts("indicator", "ndc", float(score))
        print(f"[ndc] {period} 分數={score} {light_name}")

    except Exception as e:
        print(f"[ndc] Error: {e}")
