"""Backtrader translator + run_backtest happy-path tests."""
from services.strategy_backtest import (
    BacktestResult, Trade, Summary,
    run_backtest, try_translate,
)


# ── try_translate ─────────────────────────────────────────────────────

def test_try_translate_accepts_simple_strategy(make_strategy):
    s = make_strategy(entry={
        "version": 1,
        "all": [{"left": {"field": "close"}, "op": "gt",
                 "right": {"indicator": "sma", "n": 20}}],
    })
    cls = try_translate(s)
    assert cls is not None


def test_try_translate_handles_advanced_exit(make_strategy):
    s = make_strategy(
        entry={"version": 1,
               "all": [{"left": {"field": "close"}, "op": "gt",
                        "right": {"const": 50}}]},
        stop_loss={"version": 1, "type": "dsl",
                   "all": [{"left": {"field": "close"}, "op": "lt",
                            "right": {"var": "entry_price"}}]},
    )
    cls = try_translate(s)
    assert cls is not None


# ── run_backtest: deterministic trade list over the fixture ──────────

def test_run_backtest_produces_at_least_one_trade(make_strategy, synthetic_bars):
    """SMA(5) cross above SMA(20) on a noisy-uptrend fixture should fire
    at least once over 250 bars."""
    s = make_strategy(entry={
        "version": 1,
        "all": [{"left": {"indicator": "sma", "n": 5}, "op": "cross_above",
                 "right": {"indicator": "sma", "n": 20}}],
    })
    result = run_backtest(s, bars=synthetic_bars)
    assert isinstance(result, BacktestResult)
    assert isinstance(result.summary, Summary)
    assert len(result.trades) >= 1
    for t in result.trades:
        assert isinstance(t, Trade)
        assert t.exit_reason in {"TAKE_PROFIT", "STOP_LOSS", "TIMEOUT"}


def test_run_backtest_summary_pnl_matches_trade_sum(make_strategy, synthetic_bars):
    s = make_strategy(entry={
        "version": 1,
        "all": [{"left": {"indicator": "sma", "n": 5}, "op": "cross_above",
                 "right": {"indicator": "sma", "n": 20}}],
    })
    result = run_backtest(s, bars=synthetic_bars)
    expected = sum(t.pnl_amount for t in result.trades)
    assert abs(result.summary.total_pnl_amount - expected) < 1e-3


def test_run_backtest_short_direction_flips_pnl(make_strategy, synthetic_bars):
    s_long = make_strategy(direction="long", entry={
        "version": 1,
        "all": [{"left": {"field": "close"}, "op": "gt",
                 "right": {"const": 0}}],   # always-true entry → enter on bar 1
    }, take_profit={"version": 1, "type": "pct", "value": 100.0},  # high so it never fires
       stop_loss={"version": 1, "type": "pct", "value": 100.0})
    s_short = make_strategy(direction="short", entry={
        "version": 1,
        "all": [{"left": {"field": "close"}, "op": "gt",
                 "right": {"const": 0}}],
    }, take_profit={"version": 1, "type": "pct", "value": 100.0},
       stop_loss={"version": 1, "type": "pct", "value": 100.0})

    long_res  = run_backtest(s_long,  bars=synthetic_bars)
    short_res = run_backtest(s_short, bars=synthetic_bars)
    # In a generally rising fixture, long is profitable, short is losing,
    # and direction flips the open-position PnL sign.
    assert long_res.summary.total_pnl_amount > 0
    assert short_res.summary.total_pnl_amount < 0


def test_run_backtest_empty_bars_returns_empty_trades(make_strategy):
    s = make_strategy(entry={
        "version": 1,
        "all": [{"left": {"field": "close"}, "op": "gt",
                 "right": {"const": 0}}],
    })
    result = run_backtest(s, bars=[])
    assert result.trades == []
    assert result.summary.n_trades == 0


def test_run_backtest_from_db_pulls_bars_and_runs(make_strategy):
    """Synthetic bars in futures_daily → end-to-end backtest result."""
    from repositories.futures import save_futures_daily_rows
    from services.strategy_backtest import run_backtest_from_db

    import datetime
    base = datetime.date(2026, 1, 1)
    rows = []
    for i in range(60):
        rows.append({
            "symbol": "TX",
            "date":   str(base + datetime.timedelta(days=i)),
            "contract_date": "202604",
            "open":   100.0 + i,
            "high":   100.0 + i + 2,
            "low":    100.0 + i - 2,
            "close":  100.0 + i,
            "volume": 1000,
            "open_interest": None, "settlement": None,
        })
    save_futures_daily_rows(rows)

    s = make_strategy(entry={
        "version": 1,
        "all": [{"left": {"field": "close"}, "op": "gt",
                 "right": {"const": 0}}],
    })
    res = run_backtest_from_db(s,
                               start_date="2026-01-01",
                               end_date="2026-02-28")
    assert res.summary.n_trades >= 1
