"""PER + Revenue + Financial + Dividend repository."""
import re

from db.connection import get_connection


# --- PER ---

def save_per_daily_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_per_daily (ticker, date, per, pbr, dividend_yield) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(ticker, date) DO UPDATE SET "
            " per=excluded.per, pbr=excluded.pbr, dividend_yield=excluded.dividend_yield",
            [(r["ticker"], r["date"], r.get("per"), r.get("pbr"), r.get("dividend_yield"))
             for r in rows],
        )


def get_per_daily_range(ticker: str, since_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, per, pbr, dividend_yield FROM stock_per_daily "
            "WHERE ticker=? AND date>=? ORDER BY date",
            (ticker, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_per_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_per_daily WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None


# --- Revenue ---

def save_revenue_monthly_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_revenue_monthly "
            "(ticker, year, month, revenue, announced_date) VALUES (?,?,?,?,?) "
            "ON CONFLICT(ticker, year, month) DO UPDATE SET "
            " revenue=excluded.revenue, announced_date=excluded.announced_date",
            [(r["ticker"], r["year"], r["month"], r.get("revenue"), r.get("announced_date"))
             for r in rows],
        )


def get_revenue_monthly_range(ticker: str, since_year: int, since_month: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT year, month, revenue, announced_date FROM stock_revenue_monthly "
            "WHERE ticker=? AND (year * 12 + month) >= (? * 12 + ?) "
            "ORDER BY year, month",
            (ticker, since_year, since_month),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_revenue_ym(ticker: str) -> tuple[int, int] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT year, month FROM stock_revenue_monthly "
            "WHERE ticker=? ORDER BY year DESC, month DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return (row["year"], row["month"]) if row else None


# --- Financial (income/balance/cash_flow) ---

def save_financial_quarterly_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_financial_quarterly "
            "(ticker, date, report_type, type, value) VALUES (?,?,?,?,?) "
            "ON CONFLICT(ticker, date, report_type, type) DO UPDATE SET "
            " value=excluded.value",
            [(r["ticker"], r["date"], r["report_type"], r["type"], r.get("value"))
             for r in rows],
        )


def get_financial_quarterly_range(ticker: str, report_type: str, since_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, type, value FROM stock_financial_quarterly "
            "WHERE ticker=? AND report_type=? AND date>=? "
            "ORDER BY date, type",
            (ticker, report_type, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_financial_date(ticker: str, report_type: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM stock_financial_quarterly "
            "WHERE ticker=? AND report_type=?",
            (ticker, report_type),
        ).fetchone()
        return row["d"] if row and row["d"] else None


# --- Dividend ---

def save_dividend_history_rows(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO stock_dividend_history "
            "(ticker, year, cash_dividend, stock_dividend, cash_ex_date, cash_payment_date, announcement_date) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, year) DO UPDATE SET "
            " cash_dividend=excluded.cash_dividend, "
            " stock_dividend=excluded.stock_dividend, "
            " cash_ex_date=excluded.cash_ex_date, "
            " cash_payment_date=excluded.cash_payment_date, "
            " announcement_date=excluded.announcement_date",
            [(r["ticker"], r["year"], r.get("cash_dividend"), r.get("stock_dividend"),
              r.get("cash_ex_date"), r.get("cash_payment_date"), r.get("announcement_date"))
             for r in rows],
        )


def get_dividend_history(ticker: str) -> list[dict]:
    """Return all dividend rows for ticker, sorted by ROC year + 季 numeric prefix."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT year, cash_dividend, stock_dividend, cash_ex_date, "
            "       cash_payment_date, announcement_date "
            "FROM stock_dividend_history WHERE ticker=?",
            (ticker,),
        ).fetchall()
    result = [dict(r) for r in rows]

    def _key(row: dict) -> tuple[int, int]:
        # 抓出「ROC 年」與「季」做自然排序;格式如 "114年第3季"
        y = row["year"] or ""
        ym = re.match(r"(\d+)", y)
        qm = re.search(r"第(\d+)", y)
        return (int(ym.group(1)) if ym else 0,
                int(qm.group(1)) if qm else 0)

    result.sort(key=_key)
    return result


def get_latest_dividend_announce_date(ticker: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(announcement_date) AS d FROM stock_dividend_history WHERE ticker=?",
            (ticker,),
        ).fetchone()
        return row["d"] if row and row["d"] else None
