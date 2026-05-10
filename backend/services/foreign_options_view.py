"""Shape institutional_options rows for the /foreign-flow endpoint.

The route hands us the visible date timeline (from the K-line backbone)
and the raw rows pulled from `institutional_options_daily`. We project
those rows into two complementary structures:

1. Aligned chart series — one array per (identity × put_call × side),
   indexed by `dates[]`. Frontend uses these directly with Recharts.
   Currently we only emit the four 外資 series since that's the chart's
   focus; investor breakdowns live in the detail table.
2. `detail_by_date` — per-day list of all 6 rows (3 identities × CALL/PUT)
   so the breakdown table can render any selected date in one lookup.

Amounts stay in 千元 (TAIFEX native); the frontend converts to 億元 at
render time.
"""
from collections import defaultdict


_IDENTITIES = ("foreign", "investment_trust", "dealer")
_PUT_CALLS = ("CALL", "PUT")


def _key(identity: str, put_call: str) -> tuple[str, str]:
    return (identity, put_call)


def build_options_block(
    dates: list[str], rows: list[dict],
) -> dict:
    """Return the `options` payload for tw_futures_foreign_flow.

    Args:
        dates: visible K-line dates, ascending. Acts as the canonical
            timeline; chart series are sized to match.
        rows: institutional_options_daily rows in the visible window
            (already filtered to symbol='TXO' upstream).
    """
    # Index by (date, identity, put_call) for O(1) lookup.
    by_key: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        by_key[(r["date"], r["identity"], r["put_call"])] = r

    def _series(identity: str, put_call: str, field: str) -> list[float | None]:
        out: list[float | None] = []
        for d in dates:
            r = by_key.get((d, identity, put_call))
            out.append(r[field] if r else None)
        return out

    # `detail_by_date` only includes dates we actually have data for —
    # frontend handles the missing-data case (table message).
    detail_by_date: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        detail_by_date[r["date"]].append({
            "identity":     r["identity"],
            "put_call":     r["put_call"],
            "long_oi":      int(r["long_oi"]),
            "short_oi":     int(r["short_oi"]),
            "long_amount":  float(r["long_amount"]),
            "short_amount": float(r["short_amount"]),
        })

    return {
        # Chart series — 外資 主軸，買權/賣權各 long/short 一條序列。
        "foreign_call_long_amount":  _series("foreign", "CALL", "long_amount"),
        "foreign_call_short_amount": _series("foreign", "CALL", "short_amount"),
        "foreign_put_long_amount":   _series("foreign", "PUT",  "long_amount"),
        "foreign_put_short_amount":  _series("foreign", "PUT",  "short_amount"),
        # Per-date detail for the breakdown table.
        "detail_by_date": dict(detail_by_date),
    }
