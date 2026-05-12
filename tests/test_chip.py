"""Chip fetcher tests."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import db
from main import app
from fetchers.chip_total import parse_total_margin, parse_total_institutional
from fetchers.chip_stock import parse_stock_inst, parse_stock_margin, fetch_stock_chip

client = TestClient(app)


@pytest.fixture(autouse=True)
def _watch_2330():
    """Endpoints under /api/stocks/{ticker}/* require the ticker to be in
    the user's watchlist now that auto-tracked is gone."""
    db.add_watched_ticker(1, "2330.TW")


# Sample 來自 FinMind v4 GET /data?dataset=TaiwanStockTotalMarginPurchaseShortSale
# 一天 3 筆 row(MarginPurchase / MarginPurchaseMoney / ShortSale),長格式
SAMPLE_TOTAL_MARGIN = [
    {"name": "MarginPurchase",      "date": "2026-04-29",
     "TodayBalance": 8672780,        "YesBalance": 8677088,
     "buy": 353740, "sell": 349629, "Return": 8419},
    {"name": "ShortSale",            "date": "2026-04-29",
     "TodayBalance": 197420,         "YesBalance": 197613,
     "buy": 19169,  "sell": 20523,  "Return": 1547},
    {"name": "MarginPurchaseMoney", "date": "2026-04-29",
     "TodayBalance": 460963803000,   "YesBalance": 457112797000,
     "buy": 29073808000, "sell": 24578802000, "Return": 644000000},
]


def test_parse_total_margin_returns_three_indicators_per_day():
    out = parse_total_margin(SAMPLE_TOTAL_MARGIN)
    assert "2026-04-29" in out
    day = out["2026-04-29"]
    # margin_balance: MarginPurchaseMoney TodayBalance 換算億元
    assert day["margin_balance"] == pytest.approx(4609.638, rel=1e-3)
    # short_balance: ShortSale TodayBalance 千股(直接保留為「張」)
    assert day["short_balance"] == 197420
    # short_margin_ratio: 融券張 / 融資張 × 100
    assert day["short_margin_ratio"] == pytest.approx(2.276, rel=1e-2)


# Sample 來自 FinMind v4 GET /data?dataset=TaiwanStockTotalInstitutionalInvestors
# 一天 6 筆 row,name 區分法人類別,單位是「元」
SAMPLE_TOTAL_INST = [
    {"name": "Foreign_Investor",   "date": "2026-04-29",
     "buy": 338372913624, "sell": 386520362349},
    {"name": "Foreign_Dealer_Self","date": "2026-04-29",
     "buy": 0,            "sell": 0},
    {"name": "Investment_Trust",   "date": "2026-04-29",
     "buy": 22631309887,  "sell": 20502983872},
    {"name": "Dealer_self",        "date": "2026-04-29",
     "buy": 4610504372,   "sell": 6343282634},
    {"name": "Dealer_Hedging",     "date": "2026-04-29",
     "buy": 25753523687,  "sell": 25619864056},
    {"name": "total",              "date": "2026-04-29",
     "buy": 391368251570, "sell": 438986492911},
]


def test_parse_total_institutional_returns_three_net_buys_per_day():
    out = parse_total_institutional(SAMPLE_TOTAL_INST)
    day = out["2026-04-29"]
    # 外資 = Foreign_Investor + Foreign_Dealer_Self;((338.37 - 386.52) + (0 - 0)) × 10 億 ≈ -481.47 億
    assert day["total_foreign_net"] == pytest.approx(-481.474, rel=1e-2)
    # 投信:(22.63 - 20.50)億 ≈ 21.28 億
    assert day["total_trust_net"] == pytest.approx(21.283, rel=1e-2)
    # 自營商 = Dealer_self + Dealer_Hedging;((4.61 - 6.34) + (25.75 - 25.62))億 ≈ -15.99 億
    assert day["total_dealer_net"] == pytest.approx(-15.991, rel=1e-2)


# 個股三大法人(長格式,name 區分)
SAMPLE_STOCK_INST = [
    {"date": "2026-04-29", "stock_id": "2330",
     "name": "Foreign_Investor",     "buy": 5_000_000, "sell": 3_000_000},
    {"date": "2026-04-29", "stock_id": "2330",
     "name": "Foreign_Dealer_Self",  "buy": 0,         "sell": 0},
    {"date": "2026-04-29", "stock_id": "2330",
     "name": "Investment_Trust",     "buy": 100_000,   "sell": 200_000},
    {"date": "2026-04-29", "stock_id": "2330",
     "name": "Dealer_self",          "buy": 50_000,    "sell": 80_000},
    {"date": "2026-04-29", "stock_id": "2330",
     "name": "Dealer_Hedging",       "buy": 30_000,    "sell": 20_000},
]


def test_parse_stock_inst_aggregates_to_three_net_lots():
    out = parse_stock_inst(SAMPLE_STOCK_INST, ticker="2330.TW")
    assert len(out) == 1
    row = out[0]
    assert row["ticker"] == "2330.TW"
    assert row["date"] == "2026-04-29"
    assert row["foreign_buy"]  == 5_000_000
    assert row["foreign_sell"] == 3_000_000
    assert row["trust_buy"]    == 100_000
    assert row["trust_sell"]   == 200_000
    assert row["dealer_buy"]   == 50_000 + 30_000
    assert row["dealer_sell"]  == 80_000 + 20_000


# 個股融資融券(寬格式 — 一天一筆)
SAMPLE_STOCK_MARGIN = [
    {"date": "2026-04-29", "stock_id": "2330",
     "MarginPurchaseTodayBalance": 12345,
     "ShortSaleTodayBalance": 678,
     "MarginPurchaseBuy": 100, "MarginPurchaseSell": 80,
     "ShortSaleBuy": 5, "ShortSaleSell": 7,
     "MarginPurchaseLimit": 0, "ShortSaleLimit": 0,
     "MarginPurchaseCashRepayment": 0, "ShortSaleCashRepayment": 0,
     "MarginPurchaseYesterdayBalance": 0, "ShortSaleYesterdayBalance": 0,
     "OffsetLoanAndShort": 0, "Note": ""},
]


def test_parse_stock_margin_extracts_balances():
    out = parse_stock_margin(SAMPLE_STOCK_MARGIN, ticker="2330.TW")
    assert len(out) == 1
    row = out[0]
    assert row["margin_balance"] == 12345
    assert row["short_balance"]  == 678


def _seed_chip_rows(ticker: str, days_data: list[dict]) -> None:
    """Helper:直接塞 chip rows 進 DB(略過 fetch)。"""
    rows = []
    for d in days_data:
        rows.append({
            "ticker": ticker, "date": d["date"],
            "foreign_buy":  d.get("foreign_buy"),  "foreign_sell": d.get("foreign_sell"),
            "trust_buy":    d.get("trust_buy"),    "trust_sell":   d.get("trust_sell"),
            "dealer_buy":   d.get("dealer_buy"),   "dealer_sell":  d.get("dealer_sell"),
            "margin_balance": d.get("margin_balance"),
            "short_balance":  d.get("short_balance"),
        })
    db.save_chip_daily_rows(rows)


def test_chip_endpoint_returns_net_values():
    db.init_db()
    _seed_chip_rows("2330.TW", [
        {"date": "2026-04-29",
         "foreign_buy": 5_000_000, "foreign_sell": 3_000_000,
         "trust_buy": 100_000, "trust_sell": 200_000,
         "dealer_buy": 80_000, "dealer_sell": 100_000,
         "margin_balance": 12345, "short_balance": 678},
    ])
    # patch fetch 不要打網路(app 直接引用,要 patch app 模組的名稱)
    with patch("api.routes.stocks.fetch_stock_chip", return_value=True):
        r = client.get("/api/stocks/2330.TW/chip?days=20")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "2330.TW"
    assert body["ok"] is True
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["foreign_net"] == 2_000_000
    assert row["trust_net"]   == -100_000
    assert row["dealer_net"]  == -20_000
    assert row["margin_balance"] == 12345
    assert row["short_balance"]  == 678


def test_chip_endpoint_rejects_non_taiwan_ticker():
    db.add_watched_ticker(1, "AAPL")
    r = client.get("/api/stocks/AAPL/chip")
    assert r.status_code == 400
