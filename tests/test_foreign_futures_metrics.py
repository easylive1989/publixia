"""Pure-function tests for the metric calculation service.

The formulas under test are documented in
`backend/services/foreign_futures_metrics.py` and
`docs/superpowers/specs/<this-feature>.md`.
"""
from services.foreign_futures_metrics import (
    MULT_TX, MULT_MTX, MTX_TO_TX_LOT, compute_metrics,
)


# ── synthetic factory ──────────────────────────────────────────────────

def _row(date: str, long_oi: int, short_oi: int,
         long_amt_thousand: float, short_amt_thousand: float) -> dict:
    return {
        "date": date,
        "foreign_long_oi": long_oi,
        "foreign_short_oi": short_oi,
        "foreign_long_amount":  long_amt_thousand,
        "foreign_short_amount": short_amt_thousand,
    }


def test_constants_match_contract_specs():
    assert MULT_TX == 200
    assert MULT_MTX == 50
    assert MTX_TO_TX_LOT == 0.25


def test_single_day_long_position_cost_and_unrealized():
    """Pure long, no MTX. cost = long_amt / (long_oi × 200)."""
    # 100 lots of TX entered at 16,000 → contract value 100 × 16,000 × 200
    # = 320,000,000 NT$ = 320,000 千元.
    tx = [_row("2025-05-01", long_oi=100, short_oi=0,
               long_amt_thousand=320_000.0, short_amt_thousand=0.0)]
    closes = {"2025-05-01": 16_500.0}
    out = compute_metrics(tx, [], closes)
    assert len(out) == 1
    r = out[0]
    assert r["net_position"] == 100
    assert r["cost"] == 16_000
    # (16500 - 16000) × 100 lots × 200 NT$/pt = 10,000,000 NT$
    assert r["unrealized_pnl"] == 10_000_000
    assert r["net_change"] is None      # no prior day
    assert r["realized_pnl"] == 0


def test_short_position_cost_negative_position():
    """Pure short → net_position negative, cost still in points."""
    tx = [_row("2025-05-01", long_oi=0, short_oi=50,
               long_amt_thousand=0.0, short_amt_thousand=160_000.0)]
    closes = {"2025-05-01": 15_000.0}
    out = compute_metrics(tx, [], closes)
    r = out[0]
    assert r["net_position"] == -50
    # net_value = (0 - 160_000) × 1000 = -160_000_000
    # cost = -160_000_000 / (-50 × 200) = 16,000
    assert r["cost"] == 16_000
    # (15000 - 16000) × -50 × 200 = 10_000_000  (short profits as price falls)
    assert r["unrealized_pnl"] == 10_000_000


def test_tx_plus_mtx_blended():
    """Combined TX + MTX in TX-equivalent lots; cost is a weighted blend."""
    # TX: 100 long @ 16,000 → 320_000 千元
    # MTX: 80 long @ 16,400 → 80 × 16400 × 50 / 1000 = 65_600 千元
    tx  = [_row("2025-05-01", 100, 0, 320_000.0, 0.0)]
    mtx = [_row("2025-05-01",  80, 0,  65_600.0, 0.0)]
    closes = {"2025-05-01": 16_500.0}
    out = compute_metrics(tx, mtx, closes)
    r = out[0]
    # net_position = 100 + 80/4 = 120 TX-equiv lots
    assert r["net_position"] == 120
    # net_value = (320_000 + 65_600) × 1000 = 385_600_000
    # cost = 385_600_000 / (120 × 200) = 16_066.666...
    assert abs(r["cost"] - (385_600_000 / 24_000)) < 1e-6
    # unrealized = (16500 - 16066.6667) × 120 × 200
    expected_pnl = (16_500 - 385_600_000 / 24_000) * 120 * 200
    assert abs(r["unrealized_pnl"] - expected_pnl) < 1e-6


def test_net_change_emitted_after_first_day():
    tx = [
        _row("2025-05-01", 100, 0, 320_000.0, 0.0),  # +100
        _row("2025-05-02", 130, 0, 419_500.0, 0.0),  # +130 → change = +30
    ]
    closes = {"2025-05-01": 16_500.0, "2025-05-02": 16_500.0}
    out = compute_metrics(tx, [], closes)
    assert out[0]["net_change"] is None
    assert out[1]["net_change"] == 30


def test_realized_pnl_when_long_position_shrinks():
    """Selling 40 of 100 lots locks in (today's close - yesterday cost)."""
    tx = [
        _row("2025-05-01", 100, 0, 320_000.0, 0.0),  # cost 16_000
        _row("2025-05-02",  60, 0, 192_000.0, 0.0),  # cost still 16_000
    ]
    closes = {"2025-05-01": 16_500.0, "2025-05-02": 16_300.0}
    out = compute_metrics(tx, [], closes)
    # closed_lots = max(0, 100 - 60) × sign(+) = +40
    # realized = 40 × (16300 - 16000) × 200 = 2_400_000
    assert out[1]["realized_pnl"] == 40 * 300 * 200


def test_realized_zero_when_position_grows():
    tx = [
        _row("2025-05-01", 100, 0, 320_000.0, 0.0),
        _row("2025-05-02", 150, 0, 480_000.0, 0.0),
    ]
    closes = {"2025-05-01": 16_500.0, "2025-05-02": 16_300.0}
    out = compute_metrics(tx, [], closes)
    assert out[1]["realized_pnl"] == 0


def test_flat_position_makes_cost_none_and_unrealized_none():
    tx = [_row("2025-05-01", 100, 100, 320_000.0, 320_000.0)]
    out = compute_metrics(tx, [], {"2025-05-01": 16_500.0})
    r = out[0]
    assert r["net_position"] == 0
    assert r["cost"] is None
    assert r["unrealized_pnl"] is None


def test_missing_close_makes_unrealized_none_but_position_emitted():
    tx = [_row("2025-05-01", 100, 0, 320_000.0, 0.0)]
    out = compute_metrics(tx, [], {})  # no close for the date
    r = out[0]
    assert r["net_position"] == 100
    assert r["cost"] == 16_000
    assert r["unrealized_pnl"] is None


def test_short_position_shrink_realized_pnl_sign():
    """Closing a short at a lower price (profit) → positive realized PnL."""
    tx = [
        # Day 1: short 50 at 16,000.
        _row("2025-05-01", 0, 50, 0.0, 160_000.0),
        # Day 2: short 30 (covered 20 lots) at close 15,000 (profit).
        _row("2025-05-02", 0, 30, 0.0,  96_000.0),
    ]
    closes = {"2025-05-01": 16_000.0, "2025-05-02": 15_000.0}
    out = compute_metrics(tx, [], closes)
    # closed_lots = (50 - 30) × sign(-) = -20
    # realized = -20 × (15000 - 16000) × 200 = +4_000_000
    assert out[1]["realized_pnl"] == 4_000_000
