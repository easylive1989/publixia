"""Shape txo_strike_oi rows for the /foreign-flow endpoint.

The strike-distribution chart shows a single trading day at a time:
履約價 on X, market-wide CALL/PUT OI on Y. TAIFEX publishes both monthly
(e.g. 202506) and weekly contracts (e.g. 202506W2); the chart focuses on
the near-month standard contract by default since weeklies thin out and
clutter the histogram, but we return the full breakdown so a richer
control surface can be layered on later.
"""
from collections import defaultdict


def _is_monthly(expiry_month: str) -> bool:
    """Classify a TAIFEX expiry token.

    TAIFEX uses 'YYYYMM' for the standard monthly contract and 'YYYYMMWn'
    for weekly contracts. Anything without a 'W' is treated as monthly.
    """
    return "W" not in (expiry_month or "")


def _select_near_month(expiry_months: list[str]) -> str | None:
    """Pick the nearest monthly expiry from a sorted unique list."""
    monthly = sorted(m for m in expiry_months if _is_monthly(m))
    return monthly[0] if monthly else None


def build_strike_oi_block(rows: list[dict]) -> dict:
    """Return the `oi_by_strike` payload.

    Args:
        rows: txo_strike_oi_daily rows for a single trading date,
            already filtered to symbol='TXO' upstream.

    Output structure:
        {
          "date": "YYYY-MM-DD",            # the date of `rows`, or None
          "expiry_months": [...],          # all expiries seen, sorted
          "near_month": "YYYYMM" | None,   # default selection for chart
          "by_expiry": {
            "<expiry>": {
              "strikes":     [strike, ...],         # ascending
              "call_oi":     [int | 0, ...],        # aligned with strikes
              "put_oi":      [int | 0, ...],
            },
            ...
          }
        }
    """
    if not rows:
        return {
            "date":          None,
            "expiry_months": [],
            "near_month":    None,
            "by_expiry":     {},
        }

    # Bucket: expiry → strike → {CALL: oi, PUT: oi}
    bucket: dict[str, dict[float, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"CALL": 0, "PUT": 0})
    )
    for r in rows:
        bucket[r["expiry_month"]][float(r["strike"])][r["put_call"]] = int(
            r["open_interest"] or 0
        )

    expiry_months = sorted(bucket.keys())
    by_expiry: dict[str, dict] = {}
    for exp in expiry_months:
        strikes = sorted(bucket[exp].keys())
        call_oi = [bucket[exp][s].get("CALL", 0) for s in strikes]
        put_oi  = [bucket[exp][s].get("PUT",  0) for s in strikes]
        by_expiry[exp] = {
            "strikes":  strikes,
            "call_oi":  call_oi,
            "put_oi":   put_oi,
        }

    return {
        "date":          rows[0]["date"],
        "expiry_months": expiry_months,
        "near_month":    _select_near_month(expiry_months),
        "by_expiry":     by_expiry,
    }
