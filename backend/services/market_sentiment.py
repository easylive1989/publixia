"""可重現的台股恐懼貪婪代理指數（0～100）。

這不是 MacroMicro 的專有公式。它固定使用本專案公開的 v1 方法：

* 動能 25%：5／20／60 日報酬的五年歷史百分位平均
* 距高點回撤 20%：相對近 252 日高點跌幅的五年歷史百分位
* 反向波動率 20%：20 日實現波動率百分位取反
* 市場寬度 25%：(上漲 + 0.5 × 平盤) / (上漲 + 下跌 + 平盤)
* 均線偏離 10%：收盤相對 60 日均線偏離的五年歷史百分位

每個價格因子只和「當天以前」最多 1,260 個交易日的同因子比較，避免用未來
資料決定當日分數。市場寬度本身已是 0～100 比例，不再做歷史排名。
"""
import math
import statistics

PRICE_WARMUP = 251
PERCENTILE_LOOKBACK = 1260
MIN_PERCENTILE_ROWS = 252
METHOD = "tw_fear_greed_proxy_v1"


def classify_sentiment(score: float) -> str:
    if score < 20:
        return "極度恐懼"
    if score < 40:
        return "恐懼"
    if score <= 60:
        return "中性"
    if score <= 80:
        return "貪婪"
    return "極度貪婪"


def _percent_rank(value: float, history: list[float]) -> float:
    below = sum(item < value for item in history)
    equal = sum(item == value for item in history)
    return 100.0 * (below + 0.5 * equal) / len(history)


def _price_signal(closes: list[float], index: int) -> tuple[float, ...]:
    close = closes[index]
    log_returns = [
        math.log(closes[pos] / closes[pos - 1])
        for pos in range(index - 19, index + 1)
    ]
    return (
        close / closes[index - 5] - 1,
        close / closes[index - 20] - 1,
        close / closes[index - 60] - 1,
        close / max(closes[index - 251:index + 1]) - 1,
        statistics.stdev(log_returns) * math.sqrt(252),
        close / (sum(closes[index - 59:index + 1]) / 60) - 1,
    )


def compute_sentiment(
    market_rows: list[dict], breadth_rows: list[dict],
) -> dict[str, dict]:
    """Return ``date -> reading`` only where breadth and enough history exist."""
    if len(market_rows) <= PRICE_WARMUP:
        return {}
    dates = [row["date"] for row in market_rows]
    closes = [float(row["index_close"]) for row in market_rows]
    breadth = {row["date"]: row for row in breadth_rows}

    signals: list[tuple[float, ...] | None] = [None] * len(market_rows)
    for index in range(PRICE_WARMUP, len(market_rows)):
        signals[index] = _price_signal(closes, index)

    readings: dict[str, dict] = {}
    for index in range(PRICE_WARMUP, len(market_rows)):
        date = dates[index]
        day_breadth = breadth.get(date)
        if day_breadth is None:
            continue
        history = [
            signal for signal in signals[
                max(PRICE_WARMUP, index - PERCENTILE_LOOKBACK):index
            ]
            if signal is not None
        ]
        if len(history) < MIN_PERCENTILE_ROWS:
            continue

        signal = signals[index]
        assert signal is not None
        percentiles = [
            _percent_rank(signal[pos], [item[pos] for item in history])
            for pos in range(6)
        ]
        momentum = sum(percentiles[:3]) / 3
        drawdown = percentiles[3]
        volatility = 100 - percentiles[4]
        deviation = percentiles[5]
        advancing = int(day_breadth["advancing"])
        declining = int(day_breadth["declining"])
        unchanged = int(day_breadth["unchanged"])
        total = advancing + declining + unchanged
        if total <= 0:
            continue
        breadth_score = 100 * (advancing + 0.5 * unchanged) / total
        score = (
            0.25 * momentum
            + 0.20 * drawdown
            + 0.20 * volatility
            + 0.25 * breadth_score
            + 0.10 * deviation
        )
        readings[date] = {
            "score": score,
            "label": classify_sentiment(score),
            "method": METHOD,
            "components": {
                "momentum": momentum,
                "drawdown": drawdown,
                "volatility": volatility,
                "breadth": breadth_score,
                "deviation": deviation,
            },
        }
    return readings
