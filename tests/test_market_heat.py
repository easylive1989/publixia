"""market_heat computation: regression, percentile, classification, payload."""
import math

from repositories import market_volume as repo
from services.market_heat import (
    MIN_ROWS, classify, compute_heat, fit_log_regression, get_market_heat,
    trailing_percentile,
)


def _rows_on_powerlaw(n, a=-7.75, b=1.608, bump=None):
    """n rows lying exactly on turnover = exp(a)·index^b (residual 0),
    with optional {i: multiplier} bumps to create hot/cold days."""
    rows = []
    for i in range(n):
        index = 8000.0 + 40.0 * i
        turnover = math.exp(a + b * math.log(index))
        if bump and i in bump:
            turnover *= bump[i]
        rows.append({
            "date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
            "taiex_close": index,
            "turnover": turnover,
        })
    return rows


def test_classify_band_edges_match_sheet():
    # 0.8 / 0.6 belong to the hotter band; 0.4 / 0.2 to the colder one.
    assert classify(0.85) == ("very_hot", "明顯偏熱")
    assert classify(0.8)[1] == "明顯偏熱"
    assert classify(0.79)[1] == "偏熱"
    assert classify(0.6)[1] == "偏熱"
    assert classify(0.59)[1] == "正常"
    assert classify(0.41)[1] == "正常"
    assert classify(0.4)[1] == "偏冷"
    assert classify(0.21)[1] == "偏冷"
    assert classify(0.2)[1] == "明顯偏冷"
    assert classify(0.0)[1] == "明顯偏冷"


def test_regression_recovers_powerlaw():
    a, b = fit_log_regression(_rows_on_powerlaw(200))
    assert abs(a - (-7.75)) < 1e-9
    assert abs(b - 1.608) < 1e-9


def test_trailing_percentile_is_percentrank_inc():
    residuals = [-0.08, -0.03, 0.20, 0.40, 0.15, 0.09]
    assert trailing_percentile(residuals, 0) == 0.5   # lone row: no distribution
    assert trailing_percentile(residuals, 1) == 1.0   # 1 below / (2-1)
    assert trailing_percentile(residuals, 4) == 0.5   # 2 below / (5-1)
    assert trailing_percentile(residuals, 5) == 0.4   # 2 below / (6-1)


def test_compute_heat_derives_ratio_and_residual():
    # a 3x-volume day on an otherwise perfectly-normal series
    hot_i = 150
    rows = _rows_on_powerlaw(200, bump={hot_i: 3.0})
    heat = compute_heat(rows)
    assert len(heat) == 200
    hot = heat[hot_i]
    # one outlier barely moves the 200-row fit: ratio ≈ 3, residual ≈ ln 3
    assert abs(hot["volume_ratio"] - 3.0) < 0.1
    assert abs(hot["residual"] - math.log(3.0)) < 0.05
    assert hot["percentile"] == 1.0
    assert hot["level"] == "very_hot"
    assert hot["label"] == "明顯偏熱"
    for row in heat:
        assert abs(
            row["turnover"] / row["expected_turnover"] - row["volume_ratio"]
        ) < 1e-12
        assert abs(math.log(row["volume_ratio"]) - row["residual"]) < 1e-12


def test_compute_heat_requires_min_history():
    assert compute_heat(_rows_on_powerlaw(MIN_ROWS - 1)) == []


def test_get_market_heat_payload_from_db():
    repo.upsert_days(_rows_on_powerlaw(120, bump={119: 3.0}))
    payload = get_market_heat(days=30)
    assert len(payload["days"]) == 30
    assert payload["latest"]["date"] == payload["days"][-1]["date"]
    assert payload["latest"]["label"] == "明顯偏熱"
    # date-ascending, chart-ready
    dates = [d["date"] for d in payload["days"]]
    assert dates == sorted(dates)


def test_get_market_heat_empty_db():
    assert get_market_heat() == {"latest": None, "days": []}
