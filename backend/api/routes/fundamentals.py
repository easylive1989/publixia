"""Stock fundamentals routes: valuation, revenue, financial, dividend."""
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_token, require_user
from api.routes.stocks import _gate_or_404
from repositories.fundamentals import (
    get_dividend_history, get_financial_quarterly_range,
    get_per_daily_range, get_revenue_monthly_range,
)
from fetchers.fundamentals_stock import (
    fetch_stock_dividend, fetch_stock_financial, fetch_stock_per, fetch_stock_revenue,
    to_finmind_id as fundamentals_to_finmind_id,
)

router = APIRouter(prefix="/api", tags=["fundamentals"], dependencies=[Depends(require_token)])


@router.get("/stocks/{ticker}/valuation")
def stock_valuation(ticker: str, years: int = 5,
                    user: dict = Depends(require_user)):
    """個股估值快照:PER/PBR/殖利率最新值 + 5 年百分位 + 走勢。"""
    ticker = ticker.upper()
    _gate_or_404(user["id"], ticker)
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if years < 1 or years > 10:
        raise HTTPException(status_code=400, detail="years must be 1..10")

    fetched = fetch_stock_per(ticker)
    since_date = (datetime.now(timezone.utc).date() - timedelta(days=years * 366)).isoformat()
    rows = get_per_daily_range(ticker, since_date)

    if not rows:
        return {"ticker": ticker, "years": years, "as_of": None, "ok": fetched,
                "latest": None, "range_5y": None, "rows": []}

    rows_sorted = sorted(rows, key=lambda r: r["date"])
    latest = rows_sorted[-1]

    def _stats(values: list[float]) -> dict:
        clean = [v for v in values if v is not None]
        if not clean:
            return {"min": None, "max": None, "avg": None}
        return {"min": min(clean), "max": max(clean),
                "avg": round(sum(clean) / len(clean), 4)}

    pers = [r["per"]            for r in rows_sorted if r["per"] is not None]
    pbrs = [r["pbr"]            for r in rows_sorted if r["pbr"] is not None]
    yds  = [r["dividend_yield"] for r in rows_sorted if r["dividend_yield"] is not None]

    if latest["per"] is not None and pers:
        # Inclusive percentile rank: P(X <= current_per) × 100。
        # 若 latest 為歷史最高值 → 100;若為最低 → ~ (1/N)×100。
        below = sum(1 for v in pers if v <= latest["per"])
        per_percentile = round(below / len(pers) * 100, 2)
    else:
        per_percentile = None

    return {
        "ticker": ticker, "years": years,
        "as_of": latest["date"], "ok": True,
        "latest": {
            "per": latest["per"], "pbr": latest["pbr"],
            "dividend_yield": latest["dividend_yield"],
            "per_percentile_5y": per_percentile,
        },
        "range_5y": {"per": _stats(pers), "pbr": _stats(pbrs), "dividend_yield": _stats(yds)},
        "rows": rows_sorted,
    }


@router.get("/stocks/{ticker}/revenue")
def stock_revenue(ticker: str, months: int = 36,
                  user: dict = Depends(require_user)):
    """個股月營收 + YoY + 12MA + YTD vs 去年同期。"""
    ticker = ticker.upper()
    _gate_or_404(user["id"], ticker)
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if months < 1 or months > 60:
        raise HTTPException(status_code=400, detail="months must be 1..60")

    fetched = fetch_stock_revenue(ticker)

    today = datetime.now(timezone.utc).date()
    fetch_back_months = months + 14
    since_year = today.year - (fetch_back_months // 12) - 1
    since_month = ((today.month - (fetch_back_months % 12) - 1) % 12) + 1
    rows = get_revenue_monthly_range(ticker, since_year, since_month)

    if not rows:
        return {"ticker": ticker, "months": months, "ok": fetched,
                "latest": None, "ytd": None, "rows": []}

    by_ym = {(r["year"], r["month"]): r["revenue"] for r in rows}

    def _yoy(year: int, month: int) -> float | None:
        cur = by_ym.get((year, month))
        prev = by_ym.get((year - 1, month))
        if cur is None or not prev:
            return None
        return round((cur - prev) / prev * 100, 2)

    def _ma12(year: int, month: int) -> float | None:
        vals = []
        y, m = year, month
        for _ in range(12):
            v = by_ym.get((y, m))
            if v is None:
                return None
            vals.append(v)
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return round(sum(vals) / 12, 0)

    enriched = [{
        "year":    r["year"],
        "month":   r["month"],
        "revenue": r["revenue"],
        "yoy_pct": _yoy(r["year"], r["month"]),
        "ma12":    _ma12(r["year"], r["month"]),
    } for r in rows]

    enriched_sorted = sorted(enriched, key=lambda r: (r["year"], r["month"]))
    last_n = enriched_sorted[-months:]
    latest = enriched_sorted[-1]

    def _ytd_sum(year: int, last_month: int) -> float | None:
        """Return sum 1..last_month for year; None if any month missing."""
        vals = []
        for m in range(1, last_month + 1):
            v = by_ym.get((year, m))
            if v is None:
                return None
            vals.append(v)
        return sum(vals)

    ytd_cur  = _ytd_sum(latest["year"],     latest["month"])
    ytd_prev = _ytd_sum(latest["year"] - 1, latest["month"])
    ytd_yoy = (round((ytd_cur - ytd_prev) / ytd_prev * 100, 2)
               if (ytd_cur is not None and ytd_prev) else None)

    return {
        "ticker": ticker, "months": months, "ok": True,
        "latest": latest,
        "ytd": {"accumulated": ytd_cur,
                "last_year_accumulated": ytd_prev,
                "yoy_pct": ytd_yoy},
        "rows": last_n,
    }


def _build_income_row(date: str, types: dict[str, float]) -> dict:
    rev   = types.get("Revenue")
    gp    = types.get("GrossProfit")
    op    = types.get("OperatingIncome")
    nit   = types.get("IncomeAfterTaxes")
    eps   = types.get("EPS")
    def _pct(num, den):
        return round(num / den * 100, 2) if num is not None and den else None
    return {
        "date":                  date,
        "revenue":               rev,
        "gross_profit":          gp,
        "operating_income":      op,
        "net_income":            nit,
        "eps":                   eps,
        "gross_margin_pct":      _pct(gp,  rev),
        "operating_margin_pct":  _pct(op,  rev),
        "net_margin_pct":        _pct(nit, rev),
    }


def _build_balance_row(date: str, types: dict[str, float]) -> dict:
    ta    = types.get("TotalAssets")
    ca    = types.get("CurrentAssets")
    cash  = types.get("CashAndCashEquivalents")
    tl    = types.get("Liabilities")
    cl    = types.get("CurrentLiabilities")
    ncl   = types.get("NoncurrentLiabilities")
    eq    = types.get("EquityAttributableToOwnersOfParent")
    if eq is None:
        eq = types.get("Equity")
    def _ratio(num, den):
        return round(num / den, 4) if num is not None and den else None
    def _pct(num, den):
        return round(num / den * 100, 2) if num is not None and den else None
    return {
        "date":                date,
        "total_assets":        ta,
        "current_assets":      ca,
        "cash":                cash,
        "total_liabilities":   tl,
        "current_liabilities": cl,
        "long_term_liabilities": ncl,
        "equity":              eq,
        "current_ratio":       _ratio(ca, cl),
        "debt_ratio_pct":      _pct(tl, ta),
        "equity_ratio_pct":    _pct(eq, ta),
    }


def _build_cashflow_row(date: str, types: dict[str, float]) -> dict:
    ocf = types.get("CashFlowsFromOperatingActivities")
    if ocf is None:
        ocf = types.get("NetCashInflowFromOperatingActivities")
    icf = types.get("CashProvidedByInvestingActivities")
    fcf = types.get("CashFlowsProvidedFromFinancingActivities")
    free_cf = (ocf + icf) if (ocf is not None and icf is not None) else None
    return {
        "date":           date,
        "operating_cf":   ocf,
        "investing_cf":   icf,
        "financing_cf":   fcf,
        "free_cash_flow": free_cf,
    }


_FINANCIAL_BUILDER = {
    "income":   _build_income_row,
    "balance":  _build_balance_row,
    "cashflow": _build_cashflow_row,
}


@router.get("/stocks/{ticker}/financial")
def stock_financial(ticker: str, statement: str = "income", quarters: int = 12,
                    user: dict = Depends(require_user)):
    """個股財報(三表三選一)。statement ∈ {income, balance, cashflow}。"""
    ticker = ticker.upper()
    _gate_or_404(user["id"], ticker)
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if statement not in _FINANCIAL_BUILDER:
        raise HTTPException(status_code=400, detail="statement must be income | balance | cashflow")
    if quarters < 1 or quarters > 20:
        raise HTTPException(status_code=400, detail="quarters must be 1..20")

    report_type = "cash_flow" if statement == "cashflow" else statement
    fetched = fetch_stock_financial(ticker, report_type)

    since_date = (datetime.now(timezone.utc).date() - timedelta(days=quarters * 100)).isoformat()
    long_rows = get_financial_quarterly_range(ticker, report_type, since_date)

    if not long_rows:
        return {"ticker": ticker, "statement": statement, "quarters": quarters,
                "ok": fetched, "rows": [], "annual_summary": None}

    by_date: dict[str, dict[str, float]] = {}
    for r in long_rows:
        by_date.setdefault(r["date"], {})[r["type"]] = r["value"]

    builder = _FINANCIAL_BUILDER[statement]
    wide_rows = sorted([builder(d, types) for d, types in by_date.items()],
                       key=lambda r: r["date"])
    last_n = wide_rows[-quarters:]

    annual_summary = None
    if statement == "income" and len(wide_rows) >= 8:
        last4 = wide_rows[-4:]
        prev4 = wide_rows[-8:-4]
        def _sum(rows: list[dict], key: str) -> float | None:
            vals = [r.get(key) for r in rows if r.get(key) is not None]
            return sum(vals) if vals else None
        cur_eps = _sum(last4, "eps");      prev_eps = _sum(prev4, "eps")
        cur_rev = _sum(last4, "revenue");  prev_rev = _sum(prev4, "revenue")
        annual_summary = {
            "current_4q":  {"eps": cur_eps,  "revenue": cur_rev},
            "previous_4q": {"eps": prev_eps, "revenue": prev_rev},
            "eps_yoy_pct":     round((cur_eps - prev_eps) / prev_eps * 100, 2) if (cur_eps is not None and prev_eps) else None,
            "revenue_yoy_pct": round((cur_rev - prev_rev) / prev_rev * 100, 2) if (cur_rev is not None and prev_rev) else None,
        }

    return {
        "ticker": ticker, "statement": statement, "quarters": quarters,
        "ok": True, "rows": last_n,
        "annual_summary": annual_summary,
    }


def _aggregate_dividend_by_calendar_year(rows: list[dict]) -> dict[int, dict]:
    """股利資料按 ROC 年(year 字串前綴 e.g. "114年第3季")推斷西元年,合計現金/股票股利。"""
    by_year: dict[int, dict] = {}
    for r in rows:
        y_str = r.get("year") or ""
        m = re.match(r"^(\d{2,3})年", y_str)
        if not m:
            continue
        roc_year = int(m.group(1))
        ce_year = roc_year + 1911
        bucket = by_year.setdefault(ce_year, {
            "year": ce_year, "cash_dividend": 0.0, "stock_dividend": 0.0,
            "cash_ex_date": None, "cash_payment_date": None,
        })
        bucket["cash_dividend"]  += float(r.get("cash_dividend")  or 0)
        bucket["stock_dividend"] += float(r.get("stock_dividend") or 0)
        ex = r.get("cash_ex_date")
        if ex and (bucket["cash_ex_date"] is None or ex > bucket["cash_ex_date"]):
            bucket["cash_ex_date"] = ex
            bucket["cash_payment_date"] = r.get("cash_payment_date")
    return by_year


def _annual_eps_sum(ticker: str, year: int) -> float | None:
    """回傳該西元年 EPS 合計(可能是 partial-year — 例:當年只發了 Q1+Q2 報表)。
    若 DB 中該年完全沒 EPS 資料,回 None;否則回現有季度 EPS 加總(可能 < 4 季)。
    呼叫方需注意此值在年中可能不是完整年度 EPS。
    """
    rows = get_financial_quarterly_range(ticker, "income", f"{year}-01-01")
    eps_by_date: dict[str, float] = {}
    for r in rows:
        if r["type"] == "EPS" and r["date"].startswith(str(year)):
            eps_by_date[r["date"]] = r["value"]
    if not eps_by_date:
        return None
    return round(sum(eps_by_date.values()), 4)


@router.get("/stocks/{ticker}/dividend")
def stock_dividend(ticker: str, years: int = 10,
                   user: dict = Depends(require_user)):
    """個股股利歷史:按西元年合計現金/股票股利,加配發率。"""
    ticker = ticker.upper()
    _gate_or_404(user["id"], ticker)
    if fundamentals_to_finmind_id(ticker) is None:
        raise HTTPException(status_code=400, detail="Only Taiwan tickers (.TW/.TWO) are supported")
    if years < 1 or years > 30:
        raise HTTPException(status_code=400, detail="years must be 1..30")

    fetched = fetch_stock_dividend(ticker)
    raw_rows = get_dividend_history(ticker)

    if not raw_rows:
        return {"ticker": ticker, "years": years, "ok": fetched,
                "summary": None, "rows": []}

    by_year = _aggregate_dividend_by_calendar_year(raw_rows)

    rows_with_ratio = []
    cutoff_year = datetime.now(timezone.utc).year - years
    for ce_year, b in sorted(by_year.items()):
        if ce_year < cutoff_year:
            continue
        eps_sum = _annual_eps_sum(ticker, ce_year)
        payout = (round(b["cash_dividend"] / eps_sum * 100, 2)
                  if eps_sum and eps_sum != 0 else None)
        rows_with_ratio.append({
            "year":             ce_year,
            "cash_dividend":    round(b["cash_dividend"], 4),
            "stock_dividend":   round(b["stock_dividend"], 4),
            "cash_ex_date":     b["cash_ex_date"],
            "cash_payment_date":b["cash_payment_date"],
            "payout_ratio_pct": payout,
            "dividend_yield_pct": None,
        })

    payouts = [r["payout_ratio_pct"] for r in rows_with_ratio if r["payout_ratio_pct"] is not None]
    summary = {
        "avg_payout_ratio_pct": round(sum(payouts) / len(payouts), 2) if payouts else None,
        "avg_dividend_yield_pct": None,
    }

    return {"ticker": ticker, "years": years, "ok": True,
            "summary": summary, "rows": rows_with_ratio}
