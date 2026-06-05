"""Re-normalize previously-unmatched trades.

A trade is stored with ``ticker = NULL`` whenever ``normalize()`` couldn't
resolve its raw symbol at extraction time. When the reference roster later
grows (e.g. the US SEC sync adds a ticker), those old rows can finally
resolve — this re-runs normalize over them and fills in ticker/market so
they enter price tracking. Run right after the reference sync.
"""
import logging

from repositories import trades as trades_repo
from services.normalization import normalize

logger = logging.getLogger(__name__)


def backfill_unnormalized_trades() -> dict:
    """Re-normalize every ticker-less trade; fill the ones that now resolve.

    Returns ``{"scanned": N, "filled": M}``. Does not compute price windows —
    the caller runs price tracking after, only when something was filled.
    """
    rows = trades_repo.list_unnormalized_trades()
    filled = 0
    for r in rows:
        ticker, market = normalize(r["raw_symbol"])
        if ticker:
            trades_repo.set_trade_normalization(r["id"], ticker, market)
            filled += 1
    logger.info("backfill_normalization scanned=%d filled=%d", len(rows), filled)
    return {"scanned": len(rows), "filled": filled}
