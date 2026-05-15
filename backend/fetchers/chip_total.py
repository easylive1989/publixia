"""整體市場籌碼面 fetcher。

從 FinMind 抓:
- TaiwanStockTotalMarginPurchaseShortSale (整體融資融券)
- TaiwanStockTotalInstitutionalInvestors  (整體三大法人)  ← Task 2 加上

不帶 data_id,免費 quota 內每日 1-2 個 request 即可。
寫入 indicator_snapshots 沿用既有 indicator pipeline。
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_indicator
from core.finmind import request as _request


def parse_total_margin(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Long-format → {date: {margin_balance, short_balance, short_margin_ratio}}.

    rows 每筆有 name in {MarginPurchase, MarginPurchaseMoney, ShortSale}。
    margin_balance 取自 MarginPurchaseMoney.TodayBalance(元 → 億元),
    short_balance  取自 ShortSale.TodayBalance(張),
    short_margin_ratio = ShortSale.TodayBalance / MarginPurchase.TodayBalance × 100。
    """
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        d = r.get("date")
        n = r.get("name")
        if not d or not n:
            continue
        by_day[d][n] = r

    result: dict[str, dict[str, float]] = {}
    for d, names in by_day.items():
        margin_money = names.get("MarginPurchaseMoney")
        margin_lots  = names.get("MarginPurchase")
        short        = names.get("ShortSale")
        if not (margin_money and margin_lots and short):
            continue
        margin_balance = round(float(margin_money["TodayBalance"]) / 1e8, 3)  # 元 → 億元
        short_balance = float(short["TodayBalance"])
        margin_lots_balance = float(margin_lots["TodayBalance"])
        ratio = round(short_balance / margin_lots_balance * 100, 3) if margin_lots_balance else 0
        result[d] = {
            "margin_balance":     margin_balance,
            "short_balance":      short_balance,
            "short_margin_ratio": ratio,
        }
    return result


def parse_total_institutional(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Long-format → {date: {total_foreign_net, total_trust_net, total_dealer_net}}.

    name 對應:
    - 外資  = Foreign_Investor + Foreign_Dealer_Self
    - 投信  = Investment_Trust
    - 自營商 = Dealer_self + Dealer_Hedging
    淨買超 = (buy - sell) 換算億元。
    """
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        d, n = r.get("date"), r.get("name")
        if not d or not n:
            continue
        by_day[d][n] = r

    def _net(rec: dict | None) -> float:
        if not rec:
            return 0
        return float(rec.get("buy", 0) or 0) - float(rec.get("sell", 0) or 0)

    result: dict[str, dict[str, float]] = {}
    for d, names in by_day.items():
        foreign_recs = names.get("Foreign_Investor") or names.get("Foreign_Dealer_Self")
        trust_rec    = names.get("Investment_Trust")
        dealer_recs  = names.get("Dealer_self") or names.get("Dealer_Hedging")
        if not (foreign_recs or trust_rec or dealer_recs):
            continue
        foreign = _net(names.get("Foreign_Investor")) + _net(names.get("Foreign_Dealer_Self"))
        trust   = _net(names.get("Investment_Trust"))
        dealer  = _net(names.get("Dealer_self")) + _net(names.get("Dealer_Hedging"))
        result[d] = {
            "total_foreign_net": round(foreign / 1e8, 3),
            "total_trust_net":   round(trust   / 1e8, 3),
            "total_dealer_net":  round(dealer  / 1e8, 3),
        }
    return result


def fetch_chip_total(start_date: str | None = None, end_date: str | None = None) -> None:
    """每日 cron 用:預設抓最近 5 天(涵蓋週末跳天),寫入 indicator_snapshots。

    Backfill 用:傳 start_date / end_date(YYYY-MM-DD)拉指定區間。
    """
    if not start_date:
        from datetime import timedelta
        start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

    # --- 整體融資融券 ---
    try:
        raw = _request("TaiwanStockTotalMarginPurchaseShortSale", start_date, end_date)
    except Exception as e:
        print(f"[chip_total] margin fetch error: {e}")
    else:
        margin_by_day = parse_total_margin(raw)
        for d, vals in sorted(margin_by_day.items()):
            ts = datetime.strptime(d, "%Y-%m-%d")
            margin_units = {"margin_balance": "億元", "short_balance": "張", "short_margin_ratio": "%"}
            for key in ("margin_balance", "short_balance", "short_margin_ratio"):
                save_indicator(key, vals[key],
                               json.dumps({"unit": margin_units[key], "date": d}), timestamp=ts)
        if margin_by_day:
            latest = max(margin_by_day.keys())
            print(f"[chip_total] margin {latest}: balance={margin_by_day[latest]['margin_balance']} 億, "
                  f"short={margin_by_day[latest]['short_balance']:.0f} 張, "
                  f"ratio={margin_by_day[latest]['short_margin_ratio']:.2f}%")

    # --- 整體三大法人 ---
    try:
        raw = _request("TaiwanStockTotalInstitutionalInvestors", start_date, end_date)
    except Exception as e:
        print(f"[chip_total] institutional fetch error: {e}")
    else:
        inst_by_day = parse_total_institutional(raw)
        for d, vals in sorted(inst_by_day.items()):
            ts = datetime.strptime(d, "%Y-%m-%d")
            for key in ("total_foreign_net", "total_trust_net", "total_dealer_net"):
                save_indicator(key, vals[key],
                               json.dumps({"unit": "億元", "date": d}), timestamp=ts)
        if inst_by_day:
            latest = max(inst_by_day.keys())
            print(f"[chip_total] inst {latest}: foreign={inst_by_day[latest]['total_foreign_net']} 億, "
                  f"trust={inst_by_day[latest]['total_trust_net']} 億, "
                  f"dealer={inst_by_day[latest]['total_dealer_net']} 億")
