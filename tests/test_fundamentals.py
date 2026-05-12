"""Fundamentals fetcher tests."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import db
from main import app
from fetchers.fundamentals_stock import (
    parse_per_rows, parse_revenue_rows,
    parse_financial_rows, parse_dividend_rows,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _watch_2330():
    """Endpoints under /api/stocks/{ticker}/* require the ticker to be in
    the user's watchlist now that auto-tracked is gone."""
    db.add_watched_ticker(1, "2330.TW")


# === PER ===
SAMPLE_PER = [
    {"date": "2026-04-29", "stock_id": "2330",
     "dividend_yield": 1.01, "PER": 32.91, "PBR": 10.43},
    {"date": "2026-04-30", "stock_id": "2330",
     "dividend_yield": 1.03, "PER": 32.23, "PBR": 10.22},
]


def test_parse_per_rows_extracts_three_columns():
    out = parse_per_rows(SAMPLE_PER, ticker="2330.TW")
    assert len(out) == 2
    assert out[0] == {
        "ticker": "2330.TW", "date": "2026-04-29",
        "per": 32.91, "pbr": 10.43, "dividend_yield": 1.01,
    }
    assert out[1]["per"] == 32.23


# === Revenue ===
SAMPLE_REVENUE = [
    {"date": "2026-03-01", "stock_id": "2330",
     "revenue": 317656613000, "revenue_year": 2026, "revenue_month": 2,
     "create_time": "2026-04-21"},
    {"date": "2026-04-01", "stock_id": "2330",
     "revenue": 415191699000, "revenue_year": 2026, "revenue_month": 3,
     "create_time": "2026-04-21"},
]


def test_parse_revenue_rows_extracts_year_month_value():
    out = parse_revenue_rows(SAMPLE_REVENUE, ticker="2330.TW")
    assert len(out) == 2
    first = out[0]
    assert first["ticker"]         == "2330.TW"
    assert first["year"]           == 2026
    assert first["month"]          == 2
    assert first["revenue"]        == 317656613000
    assert first["announced_date"] == "2026-04-21"


# === Financial (one parser handles all three statements via report_type) ===
SAMPLE_INCOME = [
    {"date": "2026-03-31", "stock_id": "2330", "type": "EPS",         "value": 13.98, "origin_name": "EPS"},
    {"date": "2026-03-31", "stock_id": "2330", "type": "Revenue",     "value": 8392000000000, "origin_name": "營業收入"},
    {"date": "2026-03-31", "stock_id": "2330", "type": "GrossProfit", "value": 4123000000000, "origin_name": "毛利"},
]


def test_parse_financial_rows_long_format_with_report_type():
    out = parse_financial_rows(SAMPLE_INCOME, ticker="2330.TW", report_type="income")
    assert len(out) == 3
    assert all(r["ticker"] == "2330.TW" for r in out)
    assert all(r["report_type"] == "income" for r in out)
    assert all(r["date"] == "2026-03-31" for r in out)
    types = {r["type"]: r["value"] for r in out}
    assert types["EPS"] == 13.98
    assert types["Revenue"] == 8392000000000


# === Dividend ===
SAMPLE_DIVIDEND = [
    {"date": "2025-12-17", "stock_id": "2330", "year": "114年第2季",
     "CashEarningsDistribution": 5.00001118, "StockEarningsDistribution": 0.0,
     "CashExDividendTradingDate": "2025-12-11",
     "CashDividendPaymentDate": "2026-01-08",
     "AnnouncementDate": "2025-11-26"},
    {"date": "2026-03-23", "stock_id": "2330", "year": "114年第3季",
     "CashEarningsDistribution": 6.00003573, "StockEarningsDistribution": 0.0,
     "CashExDividendTradingDate": "2026-03-17",
     "CashDividendPaymentDate": "2026-04-09",
     "AnnouncementDate": "2026-03-02"},
]


def test_parse_dividend_rows_picks_relevant_columns():
    out = parse_dividend_rows(SAMPLE_DIVIDEND, ticker="2330.TW")
    assert len(out) == 2
    first = out[0]
    assert first["ticker"]            == "2330.TW"
    assert first["year"]              == "114年第2季"
    assert first["cash_dividend"]     == pytest.approx(5.00001118)
    assert first["stock_dividend"]    == 0.0
    assert first["cash_ex_date"]      == "2025-12-11"
    assert first["cash_payment_date"] == "2026-01-08"
    assert first["announcement_date"] == "2025-11-26"


def _seed_per(ticker: str, rows: list[dict]) -> None:
    db.save_per_daily_rows([{
        "ticker": ticker, "date": r["date"],
        "per": r.get("per"), "pbr": r.get("pbr"),
        "dividend_yield": r.get("dividend_yield"),
    } for r in rows])


def _seed_revenue(ticker: str, rows: list[dict]) -> None:
    db.save_revenue_monthly_rows([{
        "ticker": ticker, "year": r["year"], "month": r["month"],
        "revenue": r.get("revenue"), "announced_date": r.get("announced_date", ""),
    } for r in rows])


def _seed_financial(ticker: str, report_type: str, rows: list[dict]) -> None:
    db.save_financial_quarterly_rows([{
        "ticker": ticker, "date": r["date"],
        "report_type": report_type, "type": r["type"], "value": r.get("value"),
    } for r in rows])


def _seed_dividend(ticker: str, rows: list[dict]) -> None:
    db.save_dividend_history_rows([{
        "ticker": ticker, "year": r["year"],
        "cash_dividend": r.get("cash_dividend"),
        "stock_dividend": r.get("stock_dividend"),
        "cash_ex_date": r.get("cash_ex_date"),
        "cash_payment_date": r.get("cash_payment_date"),
        "announcement_date": r.get("announcement_date"),
    } for r in rows])


def test_valuation_endpoint_returns_latest_and_5y_range():
    _seed_per("2330.TW", [
        {"date": "2024-01-02", "per": 20.0, "pbr": 5.0,  "dividend_yield": 2.5},
        {"date": "2024-06-30", "per": 25.0, "pbr": 6.0,  "dividend_yield": 2.0},
        {"date": "2025-06-30", "per": 30.0, "pbr": 8.0,  "dividend_yield": 1.5},
        {"date": "2026-04-30", "per": 32.0, "pbr": 10.0, "dividend_yield": 1.0},
    ])
    with patch("api.routes.fundamentals.fetch_stock_per", return_value=True):
        r = client.get("/api/stocks/2330.TW/valuation?years=5")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "2330.TW"
    assert body["ok"] is True
    assert body["latest"]["per"] == 32.0
    assert body["latest"]["pbr"] == 10.0
    assert body["latest"]["per_percentile_5y"] == pytest.approx(100.0, abs=0.01)
    assert body["range_5y"]["per"]["min"] == 20.0
    assert body["range_5y"]["per"]["max"] == 32.0
    assert len(body["rows"]) == 4


def test_revenue_endpoint_yoy_and_ytd():
    _seed_revenue("2330.TW", [
        {"year": 2025, "month": 1, "revenue": 1000_000_000_000},
        {"year": 2025, "month": 2, "revenue": 1100_000_000_000},
        {"year": 2025, "month": 3, "revenue": 1200_000_000_000},
        {"year": 2026, "month": 1, "revenue": 1500_000_000_000},
        {"year": 2026, "month": 2, "revenue": 1600_000_000_000},
    ])
    with patch("api.routes.fundamentals.fetch_stock_revenue", return_value=True):
        r = client.get("/api/stocks/2330.TW/revenue?months=12")
    body = r.json()
    assert body["latest"]["year"] == 2026
    assert body["latest"]["month"] == 2
    assert body["latest"]["yoy_pct"] == pytest.approx(45.45, abs=0.05)
    assert body["ytd"]["accumulated"] == 3100_000_000_000
    assert body["ytd"]["last_year_accumulated"] == 2100_000_000_000
    assert body["ytd"]["yoy_pct"] == pytest.approx(47.62, abs=0.05)


def test_financial_income_endpoint_returns_quarterly_with_ratios():
    _seed_financial("2330.TW", "income", [
        {"date": "2026-03-31", "type": "Revenue",         "value": 1000.0},
        {"date": "2026-03-31", "type": "GrossProfit",     "value": 600.0},
        {"date": "2026-03-31", "type": "OperatingIncome", "value": 400.0},
        {"date": "2026-03-31", "type": "IncomeAfterTaxes","value": 300.0},
        {"date": "2026-03-31", "type": "EPS",             "value": 12.5},
    ])
    with patch("api.routes.fundamentals.fetch_stock_financial", return_value=True):
        r = client.get("/api/stocks/2330.TW/financial?statement=income&quarters=4")
    body = r.json()
    assert body["ok"] is True
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["date"] == "2026-03-31"
    assert row["revenue"] == 1000.0
    assert row["gross_profit"] == 600.0
    assert row["eps"] == 12.5
    assert row["gross_margin_pct"]     == pytest.approx(60.0)
    assert row["operating_margin_pct"] == pytest.approx(40.0)
    assert row["net_margin_pct"]       == pytest.approx(30.0)


def test_financial_balance_endpoint_returns_ratios():
    _seed_financial("2330.TW", "balance", [
        {"date": "2026-03-31", "type": "TotalAssets",       "value": 5000.0},
        {"date": "2026-03-31", "type": "CurrentAssets",     "value": 2000.0},
        {"date": "2026-03-31", "type": "Liabilities",       "value": 2500.0},
        {"date": "2026-03-31", "type": "CurrentLiabilities","value": 1000.0},
        {"date": "2026-03-31", "type": "EquityAttributableToOwnersOfParent",
         "value": 2500.0},
    ])
    with patch("api.routes.fundamentals.fetch_stock_financial", return_value=True):
        r = client.get("/api/stocks/2330.TW/financial?statement=balance&quarters=4")
    body = r.json()
    row = body["rows"][0]
    assert row["total_assets"]      == 5000.0
    assert row["total_liabilities"] == 2500.0
    assert row["equity"]            == 2500.0
    assert row["current_ratio"]     == pytest.approx(2.0)
    assert row["debt_ratio_pct"]    == pytest.approx(50.0)
    assert row["equity_ratio_pct"]  == pytest.approx(50.0)
    assert body["annual_summary"] is None


def test_financial_cashflow_endpoint_returns_fcf():
    _seed_financial("2330.TW", "cash_flow", [
        {"date": "2026-03-31", "type": "CashFlowsFromOperatingActivities",     "value": 800.0},
        {"date": "2026-03-31", "type": "CashProvidedByInvestingActivities",    "value": -300.0},
        {"date": "2026-03-31", "type": "CashFlowsProvidedFromFinancingActivities", "value": -200.0},
    ])
    with patch("api.routes.fundamentals.fetch_stock_financial", return_value=True):
        r = client.get("/api/stocks/2330.TW/financial?statement=cashflow&quarters=4")
    body = r.json()
    row = body["rows"][0]
    assert row["operating_cf"]   == 800.0
    assert row["investing_cf"]   == -300.0
    assert row["financing_cf"]   == -200.0
    assert row["free_cash_flow"] == 500.0
    assert body["annual_summary"] is None


def test_dividend_endpoint_aggregates_by_calendar_year():
    _seed_dividend("2330.TW", [
        {"year": "114年第2季", "cash_dividend": 5.0, "stock_dividend": 0.0,
         "cash_ex_date": "2025-12-11", "cash_payment_date": "2026-01-08",
         "announcement_date": "2025-11-26"},
        {"year": "114年第3季", "cash_dividend": 6.0, "stock_dividend": 0.0,
         "cash_ex_date": "2026-03-17", "cash_payment_date": "2026-04-09",
         "announcement_date": "2026-03-02"},
    ])
    _seed_financial("2330.TW", "income", [
        {"date": "2025-03-31", "type": "EPS", "value": 12.0},
        {"date": "2025-06-30", "type": "EPS", "value": 12.5},
        {"date": "2025-09-30", "type": "EPS", "value": 12.5},
        {"date": "2025-12-31", "type": "EPS", "value": 13.0},
    ])
    with patch("api.routes.fundamentals.fetch_stock_dividend", return_value=True):
        r = client.get("/api/stocks/2330.TW/dividend?years=10")
    body = r.json()
    assert body["ok"] is True
    rows_by_year = {row["year"]: row for row in body["rows"]}
    row = rows_by_year[2025]
    assert row["cash_dividend"]     == 11.0
    assert row["stock_dividend"]    == 0.0
    assert row["payout_ratio_pct"]  == pytest.approx(22.0)


def test_valuation_rejects_non_taiwan_ticker():
    db.add_watched_ticker(1, "AAPL")
    r = client.get("/api/stocks/AAPL/valuation")
    assert r.status_code == 400
