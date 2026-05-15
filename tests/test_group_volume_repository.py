"""Round-trip tests for the group_volume repository."""
from repositories.group_volume import (
    save_group_volume_batch,
    get_heatmap,
)


def _agg(code: str, value: float, volume: int = 1_000, stock_count: int = 5) -> dict:
    return {
        "group_code":   code,
        "group_name":   code,
        "total_value":  value,
        "total_volume": volume,
        "stock_count":  stock_count,
    }


def _seed_one_group_over_n_days(
    code: str, start_value: float, days: list[str],
) -> None:
    """Write ``len(days)`` daily rows for one group, value incrementing by
    100 per day (so the rolling mean is easy to predict)."""
    for i, d in enumerate(days):
        save_group_volume_batch(d, "industry", [_agg(code, start_value + i * 100.0)])


def test_save_and_basic_read():
    save_group_volume_batch("2026-05-15", "industry", [
        _agg("半導體業", 100_000_000.0),
        _agg("光電業",   50_000_000.0),
    ])
    h = get_heatmap("industry", days=1, top_n=10)
    assert h["days"] == ["2026-05-15"]
    codes = [g["code"] for g in h["groups"]]
    assert codes == ["半導體業", "光電業"]   # sorted by total_value DESC
    assert h["groups"][0]["latest_value"] == 100_000_000.0
    assert h["groups"][0]["pct_series"] == [None]  # < 20 prior days


def test_mean_20d_is_null_until_twenty_prior_days_exist():
    dates = [f"2026-04-{d:02d}" for d in range(1, 22)]   # 21 dates
    _seed_one_group_over_n_days("Semiconductors", 1000.0, dates)

    # On day 20 (index 19) there are 19 prior rows → mean still NULL.
    h_partial = get_heatmap("industry", days=21, top_n=5)
    series = h_partial["groups"][0]["pct_series"]
    # First 20 entries (indexes 0..19) should be None; entry 20 should be set.
    assert all(p is None for p in series[:20])
    assert series[20] is not None


def test_pct_vs_mean_20d_math():
    """Set up: 20 prior days at value=1000 each → mean=1000. Day 21
    writes value=1200 → pct should be 0.2."""
    dates = [f"2026-04-{d:02d}" for d in range(1, 21)]   # 20 dates
    for d in dates:
        save_group_volume_batch(d, "industry", [_agg("S", 1000.0)])
    save_group_volume_batch("2026-04-21", "industry", [_agg("S", 1200.0)])

    h = get_heatmap("industry", days=1, top_n=1)
    assert h["groups"][0]["pct_series"] == [0.2]


def test_get_heatmap_picks_top_n_by_latest_date_value():
    save_group_volume_batch("2026-05-15", "industry", [
        _agg("A", 100.0),
        _agg("B", 500.0),
        _agg("C", 300.0),
        _agg("D",  50.0),
    ])
    h = get_heatmap("industry", days=1, top_n=2)
    assert [g["code"] for g in h["groups"]] == ["B", "C"]


def test_get_heatmap_aligns_pct_series_with_days():
    """Each group's pct_series must be aligned positionally to days[].
    A group that skipped one of the days gets None at that slot.
    """
    # Day 1: only A; Day 2: A + B; Day 3: A + B.
    save_group_volume_batch("2026-05-13", "industry", [_agg("A", 100.0)])
    save_group_volume_batch("2026-05-14", "industry", [_agg("A", 110.0), _agg("B", 80.0)])
    save_group_volume_batch("2026-05-15", "industry", [_agg("A", 120.0), _agg("B", 200.0)])

    h = get_heatmap("industry", days=3, top_n=2)
    assert h["days"] == ["2026-05-13", "2026-05-14", "2026-05-15"]
    # B is top by latest value (200 > 120).
    b = next(g for g in h["groups"] if g["code"] == "B")
    # B has no row on day 1 → first slot is None.
    assert b["pct_series"][0] is None
    # All series have length 3.
    for g in h["groups"]:
        assert len(g["pct_series"]) == 3


def test_get_heatmap_empty_when_no_rows():
    h = get_heatmap("industry", days=5, top_n=10)
    assert h == {"type": "industry", "days": [], "groups": []}


def test_save_is_idempotent_on_repeat():
    save_group_volume_batch("2026-05-15", "industry", [_agg("X", 100.0)])
    save_group_volume_batch("2026-05-15", "industry", [_agg("X", 200.0)])  # rewrite
    h = get_heatmap("industry", days=1, top_n=10)
    assert len(h["groups"]) == 1
    assert h["groups"][0]["latest_value"] == 200.0


def test_save_returns_count():
    n = save_group_volume_batch("2026-05-15", "industry", [
        _agg("A", 1.0), _agg("B", 2.0), _agg("C", 3.0),
    ])
    assert n == 3
    assert save_group_volume_batch("2026-05-15", "industry", []) == 0


def test_group_type_isolates_industry_vs_theme():
    save_group_volume_batch("2026-05-15", "industry", [_agg("半導體業", 100.0)])
    save_group_volume_batch("2026-05-15", "theme",    [_agg("AI",       999.0)])

    industry = get_heatmap("industry", days=1, top_n=10)
    theme    = get_heatmap("theme",    days=1, top_n=10)
    assert [g["code"] for g in industry["groups"]] == ["半導體業"]
    assert [g["code"] for g in theme["groups"]]    == ["AI"]
