"""Pure-function metric calculations for the foreign-investor futures-flow page.

Takes raw TAIFEX-style snapshots (TX + MTX foreign long/short open
interest in lots, contract amounts in 千元) plus the TX daily close
series, and emits the per-day series the frontend consumes:

- net_position: TX-equivalent lots (MTX lots are scaled by 1/4)
- cost:         blended weighted-average position cost in points
                (None when net_position is zero)
- net_change:   day-over-day delta of net_position
- unrealized_pnl: (close - cost) * net_position * MULT_TX   (NT$)
- realized_pnl:   |Δ position when shrinking| × (close - prior cost) × MULT_TX
                  (近似算法; the page renders a 註明 explaining the diff
                  from商業網站 figures.)

Kept dependency-free so it's trivial to unit-test.
"""
from __future__ import annotations

from typing import Iterable, TypedDict


MULT_TX = 200    # NT$ per TX point per lot
MULT_MTX = 50    # NT$ per MTX point per lot
MTX_TO_TX_LOT = MULT_MTX / MULT_TX  # 0.25 — 1 MTX lot is 1/4 of a TX lot


class MetricRow(TypedDict):
    date: str
    close: float | None
    net_position: float          # TX-equivalent lots
    cost: float | None           # points (None when net is flat)
    net_change: float | None     # TX-equivalent lots; None on first day
    unrealized_pnl: float | None # NT$; None when cost is None
    realized_pnl: float          # NT$; 0 on first day or when not shrinking


def _to_by_date(rows: Iterable[dict]) -> dict[str, dict]:
    return {r["date"]: r for r in rows}


def _net_position_and_value(
    tx_row: dict | None, mtx_row: dict | None,
) -> tuple[float, float]:
    """Return (net_position_in_TX_lots, net_value_TWD).

    net_value is the signed contract value in NT$ (千元 → 元 done here).
    """
    long_oi   = (tx_row["foreign_long_oi"]      if tx_row  else 0)
    short_oi  = (tx_row["foreign_short_oi"]     if tx_row  else 0)
    long_amt  = (tx_row["foreign_long_amount"]  if tx_row  else 0.0)
    short_amt = (tx_row["foreign_short_amount"] if tx_row  else 0.0)

    m_long_oi   = (mtx_row["foreign_long_oi"]      if mtx_row else 0)
    m_short_oi  = (mtx_row["foreign_short_oi"]     if mtx_row else 0)
    m_long_amt  = (mtx_row["foreign_long_amount"]  if mtx_row else 0.0)
    m_short_amt = (mtx_row["foreign_short_amount"] if mtx_row else 0.0)

    net_position = (long_oi - short_oi) + (m_long_oi - m_short_oi) * MTX_TO_TX_LOT
    # 千元 → 元 to keep PnL units consistent with MULT_TX (NT$/point).
    net_value_twd = ((long_amt - short_amt) + (m_long_amt - m_short_amt)) * 1000.0
    return net_position, net_value_twd


def _cost_per_point(net_position: float, net_value_twd: float) -> float | None:
    """Blended weighted-average cost in TX points; None when flat."""
    if net_position == 0:
        return None
    return net_value_twd / (net_position * MULT_TX)


def compute_metrics(
    tx_rows: list[dict],
    mtx_rows: list[dict],
    tx_closes: dict[str, float],
) -> list[MetricRow]:
    """Compose the four series the frontend renders.

    tx_rows / mtx_rows: ordered list of dicts from
      get_institutional_futures_range(); may be missing days for one
      symbol relative to the other.
    tx_closes: {date: close_price} from futures_daily for symbol=TX.

    Output is sorted by date over the union of dates that appear in
    either institutional series. A row whose date has no TX close still
    emits net_position/cost/net_change but unrealized_pnl is None.
    """
    tx_by_date  = _to_by_date(tx_rows)
    mtx_by_date = _to_by_date(mtx_rows)
    all_dates = sorted(set(tx_by_date) | set(mtx_by_date))

    out: list[MetricRow] = []
    prev_position: float | None = None
    prev_cost: float | None = None

    for d in all_dates:
        net_position, net_value_twd = _net_position_and_value(
            tx_by_date.get(d), mtx_by_date.get(d),
        )
        cost = _cost_per_point(net_position, net_value_twd)
        close = tx_closes.get(d)

        unrealized: float | None = None
        if cost is not None and close is not None:
            unrealized = (close - cost) * net_position * MULT_TX

        net_change: float | None = None
        if prev_position is not None:
            net_change = net_position - prev_position

        realized: float = 0.0
        if (
            prev_position is not None
            and prev_cost is not None
            and close is not None
        ):
            shrink = max(0.0, abs(prev_position) - abs(net_position))
            if shrink > 0:
                sign = 1.0 if prev_position > 0 else -1.0
                closed_lots = shrink * sign
                realized = closed_lots * (close - prev_cost) * MULT_TX

        out.append(MetricRow(
            date=d,
            close=close,
            net_position=net_position,
            cost=cost,
            net_change=net_change,
            unrealized_pnl=unrealized,
            realized_pnl=realized,
        ))

        prev_position = net_position
        prev_cost = cost if cost is not None else prev_cost

    return out


def compute_retail_ratio(rows: list[dict]) -> dict[str, float]:
    """散戶多空比 from TAIFEX 大額交易人未沖銷部位結構表 (TX combined).

    rows: ordered list of dicts from `get_large_trader_range()`.
    Returns {date: ratio_percent} where
        retail_long  = market_oi - top10_long_oi
        retail_short = market_oi - top10_short_oi
        ratio        = (retail_long - retail_short) / market_oi × 100
                     = (top10_short_oi - top10_long_oi) / market_oi × 100
    Days with market_oi == 0 are skipped.
    """
    out: dict[str, float] = {}
    for r in rows:
        market = r.get("market_oi") or 0
        if market <= 0:
            continue
        ratio = (r["top10_short_oi"] - r["top10_long_oi"]) / market * 100.0
        out[r["date"]] = ratio
    return out
