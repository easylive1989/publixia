"""DSL → Backtrader Strategy class translator + run_backtest helper.

`try_translate(strategy)` constructs a bt.Strategy subclass without
running cerebro; used by validator.translatability_check.

`run_backtest(strategy, bars=...)` runs Cerebro on the supplied bar list
(in tests) or — once P3 wires it up — on bars from the futures_daily
table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date
from typing import Sequence

import backtrader as bt
import pandas as pd

from services.strategy_dsl.models import (
    ConstExpr, FieldExpr, VarExpr,
    IndicatorSMA, IndicatorEMA, IndicatorRSI, IndicatorMACD,
    IndicatorBBands, IndicatorATR, IndicatorKD,
    IndicatorHighest, IndicatorLowest, IndicatorChangePct,
    EntryDSL, ExitDSL_Pct, ExitDSL_Points, ExitDSL_Advanced,
    DSLCondition,
)
from services.strategy_dsl.validator import validate
from core.contracts import MULTIPLIER


# ── public dataclasses ──────────────────────────────────────────────

@dataclass
class Trade:
    entry_date:    Date
    entry_price:   float
    exit_date:     Date
    exit_price:    float
    exit_reason:   str           # TAKE_PROFIT / STOP_LOSS / TIMEOUT
    held_bars:     int
    pnl_points:    float
    pnl_amount:    float
    from_stop:     bool = False  # True iff synthesised by stop() for open positions


@dataclass
class Summary:
    total_pnl_amount: float
    win_rate:         float
    avg_win_points:   float
    avg_loss_points:  float
    profit_factor:    float
    max_drawdown_amt: float
    max_drawdown_pct: float
    n_trades:         int
    avg_held_bars:    float


@dataclass
class EquityPoint:
    date:   Date
    pnl:    float


@dataclass
class BacktestResult:
    trades:       list[Trade]
    summary:      Summary
    equity_curve: list[EquityPoint] = field(default_factory=list)
    benchmark:    list[EquityPoint] = field(default_factory=list)
    warnings:     list[str]         = field(default_factory=list)


# ── translator ──────────────────────────────────────────────────────

def try_translate(strategy) -> type[bt.Strategy]:
    """Build a bt.Strategy subclass for `strategy`. Validates the DSLs
    along the way (raises DSLValidationError on bad shape)."""
    entry  = validate(strategy.entry_dsl,       kind="entry")
    tp     = validate(strategy.take_profit_dsl, kind="take_profit")
    sl     = validate(strategy.stop_loss_dsl,   kind="stop_loss")
    return _build_bt_strategy_class(
        entry=entry, take_profit=tp, stop_loss=sl,
        direction=strategy.direction,
        contract_size=strategy.contract_size,
        max_hold_days=strategy.max_hold_days,
    )


def _build_bt_strategy_class(*, entry, take_profit, stop_loss,
                             direction, contract_size, max_hold_days
                             ) -> type[bt.Strategy]:

    class _GeneratedStrategy(bt.Strategy):
        params = (
            ("direction",     direction),
            ("contract_size", contract_size),
            ("max_hold_days", max_hold_days),
        )

        def __init__(self):
            self._ind_cache: dict[str, object] = {}
            for cond in entry.all:
                self._materialize_for(cond)
            if isinstance(take_profit, ExitDSL_Advanced):
                for cond in take_profit.all:
                    self._materialize_for(cond)
            if isinstance(stop_loss, ExitDSL_Advanced):
                for cond in stop_loss.all:
                    self._materialize_for(cond)
            self._entry_bar_idx: int | None = None
            self._exit_reason: str | None = None
            self._trade_log: list[Trade] = []

        # ── indicator materialisation ────────────────────────────

        def _materialize_for(self, cond: DSLCondition):
            for expr in (cond.left, cond.right):
                self._ensure_indicator(expr)

        def _ensure_indicator(self, expr):
            """Build & cache a bt indicator for `expr` if it is one;
            non-indicator nodes (field/const/var) get cache_key=None
            and are skipped — they're resolved directly in next()."""
            key = _expr_cache_key(expr)
            if key is None or key in self._ind_cache:
                return
            self._ind_cache[key] = _build_bt_indicator(expr, self.data)

        # ── core lifecycle ───────────────────────────────────────

        def next(self):
            if self.position:
                self._maybe_exit()
            else:
                self._maybe_entry()

        def _maybe_entry(self):
            if not self._evaluate_dsl(entry, entry_price=None):
                return
            size = self.p.contract_size
            if self.p.direction == "long":
                self.buy(size=size, exectype=bt.Order.Market)
            else:
                self.sell(size=size, exectype=bt.Order.Market)
            self._entry_bar_idx = len(self)

        def _maybe_exit(self):
            entry_price = self.position.price
            if self._evaluate_exit(stop_loss, entry_price, "stop_loss"):
                self._exit_reason = "STOP_LOSS"
                self.close(exectype=bt.Order.Market)
                return
            if self._evaluate_exit(take_profit, entry_price, "take_profit"):
                self._exit_reason = "TAKE_PROFIT"
                self.close(exectype=bt.Order.Market)
                return
            if self.p.max_hold_days is not None and self._entry_bar_idx is not None:
                held = len(self) - self._entry_bar_idx
                if held >= self.p.max_hold_days:
                    self._exit_reason = "TIMEOUT"
                    self.close(exectype=bt.Order.Market)

        # ── DSL evaluation ──────────────────────────────────────

        def _evaluate_dsl(self, dsl: EntryDSL, *, entry_price: float | None) -> bool:
            for cond in dsl.all:
                if not self._evaluate_condition(cond, entry_price=entry_price):
                    return False
            return True

        def _evaluate_exit(self, dsl, entry_price: float, kind: str) -> bool:
            if isinstance(dsl, ExitDSL_Pct):
                return _check_simple_threshold(
                    self.data.close[0], entry_price, self.p.direction,
                    kind, pct=dsl.value, points=None,
                )
            if isinstance(dsl, ExitDSL_Points):
                return _check_simple_threshold(
                    self.data.close[0], entry_price, self.p.direction,
                    kind, pct=None, points=dsl.value,
                )
            return self._evaluate_dsl(
                EntryDSL(version=1, all=dsl.all), entry_price=entry_price,
            )

        def _evaluate_condition(self, cond: DSLCondition,
                                *, entry_price: float | None) -> bool:
            op = cond.op

            def value(expr, offset=0):
                return _resolve_expr(expr, self.data, self._ind_cache,
                                     entry_price, offset=offset)

            if op in ("gt", "gte", "lt", "lte"):
                l = value(cond.left)
                r = value(cond.right)
                if l is None or r is None:
                    return False
                if op == "gt":  return l >  r
                if op == "gte": return l >= r
                if op == "lt":  return l <  r
                return l <= r
            if op in ("cross_above", "cross_below"):
                l_now,  r_now  = value(cond.left), value(cond.right)
                l_prev, r_prev = value(cond.left, offset=-1), value(cond.right, offset=-1)
                if any(x is None for x in (l_now, r_now, l_prev, r_prev)):
                    return False
                if op == "cross_above":
                    return l_now > r_now and l_prev <= r_prev
                return l_now < r_now and l_prev >= r_prev
            if op in ("streak_above", "streak_below"):
                n = cond.n or 1
                for k in range(n):
                    l = value(cond.left, offset=-k)
                    r = value(cond.right, offset=-k)
                    if l is None or r is None:
                        return False
                    if op == "streak_above" and not (l >= r):
                        return False
                    if op == "streak_below" and not (l <= r):
                        return False
                return True
            return False

        # ── trade logging ───────────────────────────────────────

        def stop(self):
            """Log any position still open at end of data as TIMEOUT."""
            if self.position and self._entry_bar_idx is not None:
                entry_price = self.position.price
                exit_price  = self.data.close[0]
                held = len(self) - self._entry_bar_idx
                if self.p.direction == "long":
                    pnl_points = exit_price - entry_price
                else:
                    pnl_points = entry_price - exit_price
                self._trade_log.append(Trade(
                    entry_date=bt.num2date(self.data.datetime[-held]).date()
                    if held > 0 else self.data.datetime.date(0),
                    entry_price=entry_price,
                    exit_date=self.data.datetime.date(0),
                    exit_price=exit_price,
                    exit_reason="TIMEOUT",
                    held_bars=held,
                    pnl_points=pnl_points,
                    pnl_amount=pnl_points * self._multiplier() * self.p.contract_size,
                    from_stop=True,
                ))

        def notify_trade(self, trade):
            if not trade.isclosed:
                return
            entry_dt = bt.num2date(trade.dtopen).date()
            exit_dt  = bt.num2date(trade.dtclose).date()
            entry_price = trade.price
            exit_price = self.data.close[0]
            held = len(self) - (self._entry_bar_idx or 0)
            if self.p.direction == "long":
                pnl_points = exit_price - entry_price
            else:
                pnl_points = entry_price - exit_price
            self._trade_log.append(Trade(
                entry_date=entry_dt,
                entry_price=entry_price,
                exit_date=exit_dt,
                exit_price=exit_price,
                exit_reason=self._exit_reason or "TIMEOUT",
                held_bars=held,
                pnl_points=pnl_points,
                pnl_amount=pnl_points * self._multiplier() * self.p.contract_size,
            ))
            self._exit_reason = None
            self._entry_bar_idx = None

        def _multiplier(self) -> int:
            return MULTIPLIER.get(getattr(self, "_contract", "TX"), 200)

    return _GeneratedStrategy


# ── expression resolution inside Backtrader's next() ───────────────

def _resolve_expr(expr, data, ind_cache, entry_price, *, offset: int):
    if isinstance(expr, FieldExpr):
        line = getattr(data, expr.field, None)
        if line is None:
            return None
        try:
            return float(line[offset])
        except IndexError:
            return None
    if isinstance(expr, ConstExpr):
        return float(expr.const)
    if isinstance(expr, VarExpr):
        return float(entry_price) if entry_price is not None else None
    key = _expr_cache_key(expr)
    if key is None:
        return None
    ind = ind_cache.get(key)
    if ind is None:
        return None
    try:
        return float(ind[offset])
    except (IndexError, ValueError):
        return None


def _expr_cache_key(expr) -> str | None:
    if isinstance(expr, IndicatorSMA):       return f"sma:{expr.n}"
    if isinstance(expr, IndicatorEMA):       return f"ema:{expr.n}"
    if isinstance(expr, IndicatorRSI):       return f"rsi:{expr.n}"
    if isinstance(expr, IndicatorMACD):      return f"macd:{expr.fast}:{expr.slow}:{expr.signal}:{expr.output}"
    if isinstance(expr, IndicatorBBands):    return f"bb:{expr.n}:{expr.k}:{expr.output}"
    if isinstance(expr, IndicatorATR):       return f"atr:{expr.n}"
    if isinstance(expr, IndicatorKD):        return f"kd:{expr.n}:{expr.output}"
    if isinstance(expr, IndicatorHighest):   return f"hi:{expr.n}"
    if isinstance(expr, IndicatorLowest):    return f"lo:{expr.n}"
    if isinstance(expr, IndicatorChangePct): return f"chg:{expr.n}"
    return None


def _build_bt_indicator(expr, data):
    if isinstance(expr, IndicatorSMA):
        return bt.indicators.SMA(data.close, period=expr.n)
    if isinstance(expr, IndicatorEMA):
        return bt.indicators.EMA(data.close, period=expr.n)
    if isinstance(expr, IndicatorRSI):
        return bt.indicators.RSI(data.close, period=expr.n)
    if isinstance(expr, IndicatorMACD):
        macd = bt.indicators.MACD(data.close,
                                  period_me1=expr.fast,
                                  period_me2=expr.slow,
                                  period_signal=expr.signal)
        if expr.output == "macd":   return macd.macd
        if expr.output == "signal": return macd.signal
        return macd.macd - macd.signal
    if isinstance(expr, IndicatorBBands):
        bb = bt.indicators.BollingerBands(data.close, period=expr.n,
                                          devfactor=expr.k)
        if expr.output == "upper": return bb.top
        if expr.output == "middle": return bb.mid
        return bb.bot
    if isinstance(expr, IndicatorATR):
        return bt.indicators.ATR(data, period=expr.n)
    if isinstance(expr, IndicatorKD):
        st = bt.indicators.Stochastic(data, period=expr.n)
        return st.percK if expr.output == "k" else st.percD
    if isinstance(expr, IndicatorHighest):
        return bt.indicators.Highest(data.high, period=expr.n)
    if isinstance(expr, IndicatorLowest):
        return bt.indicators.Lowest(data.low, period=expr.n)
    if isinstance(expr, IndicatorChangePct):
        return _ChangePct(data.close, period=expr.n)
    raise TypeError(f"unknown indicator expr {type(expr).__name__}")


class _ChangePct(bt.Indicator):
    """(close - close[-period]) / close[-period] * 100"""
    lines = ("pct",)
    params = (("period", 1),)

    def next(self):
        prev = self.data[-self.p.period]
        cur = self.data[0]
        self.lines.pct[0] = (cur - prev) / prev * 100.0 if prev else 0.0


def _check_simple_threshold(close, entry_price, direction, kind, *,
                            pct, points):
    offset = entry_price * (pct / 100.0) if pct is not None else float(points)
    if direction == "long":
        if kind == "take_profit":
            return close >= entry_price + offset
        return close <= entry_price - offset
    if kind == "take_profit":
        return close <= entry_price - offset
    return close >= entry_price + offset


# ── public entrypoint ──────────────────────────────────────────────

def run_backtest(strategy, *, bars: Sequence[dict]) -> BacktestResult:
    """Run a backtest on an in-memory bar list. P3 will add a variant
    that loads from futures_daily; this signature is the test-friendly
    one and the future caller will reuse it after assembling bars."""
    if not bars:
        return BacktestResult(
            trades=[],
            summary=Summary(
                total_pnl_amount=0.0, win_rate=0.0,
                avg_win_points=0.0, avg_loss_points=0.0,
                profit_factor=0.0, max_drawdown_amt=0.0,
                max_drawdown_pct=0.0, n_trades=0, avg_held_bars=0.0,
            ),
        )

    df = pd.DataFrame(bars)
    df["datetime"] = pd.to_datetime(df["date"])
    df = df.set_index("datetime")[["open", "high", "low", "close", "volume"]]

    cerebro = bt.Cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=df,
                                        timeframe=bt.TimeFrame.Days,
                                        compression=1))
    cls = try_translate(strategy)
    # Stash contract on the class so notify_trade can compute multiplier.
    cls._contract = strategy.contract  # type: ignore[attr-defined]
    cerebro.addstrategy(cls)
    cerebro.broker.set_cash(10_000_000)
    cerebro.broker.setcommission(commission=0.0,
                                 mult=MULTIPLIER[strategy.contract])

    result = cerebro.run()
    bt_strat = result[0]
    trades: list[Trade] = list(bt_strat._trade_log)

    summary = _summarise(trades)
    return BacktestResult(trades=trades, summary=summary)


def _summarise(trades: list[Trade]) -> Summary:
    if not trades:
        return Summary(
            total_pnl_amount=0.0, win_rate=0.0,
            avg_win_points=0.0, avg_loss_points=0.0,
            profit_factor=0.0, max_drawdown_amt=0.0,
            max_drawdown_pct=0.0, n_trades=0, avg_held_bars=0.0,
        )
    wins   = [t for t in trades if t.pnl_points > 0]
    losses = [t for t in trades if t.pnl_points < 0]
    avg_win  = sum(t.pnl_points for t in wins)   / len(wins)   if wins else 0.0
    avg_loss = sum(t.pnl_points for t in losses) / len(losses) if losses else 0.0
    total_w = sum(t.pnl_amount for t in wins)
    total_l = -sum(t.pnl_amount for t in losses)
    pf = total_w / total_l if total_l > 0 else 0.0

    cumulative = 0.0
    peak = 0.0
    max_dd_amt = 0.0
    max_dd_pct = 0.0
    for t in trades:
        cumulative += t.pnl_amount
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd_amt = max(max_dd_amt, dd)
        if peak > 0:
            max_dd_pct = max(max_dd_pct, dd / peak * 100.0)

    return Summary(
        total_pnl_amount=sum(t.pnl_amount for t in trades),
        win_rate=len(wins) / len(trades) * 100.0,
        avg_win_points=avg_win,
        avg_loss_points=avg_loss,
        profit_factor=pf,
        max_drawdown_amt=max_dd_amt,
        max_drawdown_pct=max_dd_pct,
        n_trades=len(trades),
        avg_held_bars=sum(t.held_bars for t in trades) / len(trades),
    )
