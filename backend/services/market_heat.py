"""大盤成交金額冷熱判讀 (market volume heat).

Method (ported from the reference Google Sheet):

1. 位階常態 — OLS of ln(量能) on ln(指數) over the full history:
   expected turnover at today's index level. Volume grows superlinearly with
   the index (台股成交金額的擬合斜率 ≈ 1.6), so a raw moving average would
   misread every rally as "hot"; regressing on the index level removes that
   drift.
2. 量能比 = 量能 / 位階常態; 殘差 = ln(量能比).
3. 近一年百分位 — PERCENTRANK.INC of today's residual within the trailing
   ``WINDOW`` trading days (incl. today): share of the window strictly below
   today, over window size - 1.
4. 判讀 — five bands on the percentile:
   ≥0.8 明顯偏熱 / ≥0.6 偏熱 / >0.4 正常 / >0.2 偏冷 / else 明顯偏冷.

模型本身跟市場無關 —— 它只吃「指數收盤 + 當日量能」，每個市場各自用自己的
歷史迴歸、自己的近一年分佈排百分位，所以 TW 存成交金額（億元）、US 存成交
股數（億股）並不衝突：兩邊的殘差都是「相對自己的位階常態偏離多少」，本來就
不跨市場比較。

Everything is derived on read from the raw ``market_volume_daily`` rows —
nothing here persists, so the regression always reflects the full history.
"""
import math

from core.markets import TW
from repositories import market_volume as repo

# 今日 + 前 240 個交易日 ≈ 近一年。
WINDOW = 241
# 迴歸至少要跨過一段位階與量能循環才有意義。
MIN_ROWS = 60

# (lower-bound check, level key, 中文判讀) — evaluated top-down.
_LEVELS: list[tuple[float, str, str]] = [
    (0.8, "very_hot", "明顯偏熱"),
    (0.6, "hot", "偏熱"),
    (0.4, "normal", "正常"),
    (0.2, "cold", "偏冷"),
]


def classify(percentile: float) -> tuple[str, str]:
    """Percentile → (level key, 中文判讀). Band edges follow the sheet:
    0.8/0.6 belong to the hotter band, 0.4/0.2 to the colder one."""
    if percentile >= 0.8:
        return "very_hot", "明顯偏熱"
    if percentile >= 0.6:
        return "hot", "偏熱"
    if percentile > 0.4:
        return "normal", "正常"
    if percentile > 0.2:
        return "cold", "偏冷"
    return "very_cold", "明顯偏冷"


def fit_log_regression(rows: list[dict]) -> tuple[float, float]:
    """OLS ln(turnover) = a + b·ln(index_close). Returns (a, b)."""
    xs = [math.log(r["index_close"]) for r in rows]
    ys = [math.log(r["turnover"]) for r in rows]
    n = len(rows)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def trailing_percentile(residuals: list[float], i: int) -> float:
    """PERCENTRANK.INC of residuals[i] within its trailing WINDOW slice
    (inclusive of i). A lone first row has no distribution → 0.5."""
    window = residuals[max(0, i - WINDOW + 1): i + 1]
    if len(window) == 1:
        return 0.5
    below = sum(1 for r in window if r < residuals[i])
    return below / (len(window) - 1)


def compute_heat(rows: list[dict]) -> list[dict]:
    """Derive expected/ratio/residual/percentile/level for date-ascending
    raw rows. Returns [] when there's too little history to regress on."""
    if len(rows) < MIN_ROWS:
        return []
    a, b = fit_log_regression(rows)
    residuals: list[float] = []
    out: list[dict] = []
    for r in rows:
        expected = math.exp(a + b * math.log(r["index_close"]))
        residual = math.log(r["turnover"] / expected)
        residuals.append(residual)
        out.append({
            "date": r["date"],
            "index_close": r["index_close"],
            "turnover": r["turnover"],
            "expected_turnover": expected,
            "volume_ratio": r["turnover"] / expected,
            "residual": residual,
        })
    for i, row in enumerate(out):
        p = trailing_percentile(residuals, i)
        level, label = classify(p)
        row["percentile"] = p
        row["level"] = level
        row["label"] = label
    return out


def get_market_heat(days: int | None = None, market: str = TW) -> dict:
    """API payload: the latest reading + the last ``days`` readings
    (date-ascending, chart-ready). ``days=None`` returns the full history."""
    heat = compute_heat(repo.list_days(market))
    return {
        "market": market,
        "latest": heat[-1] if heat else None,
        "days": heat[-days:] if days else heat,
    }
