"""Resolve a raw stock string to a canonical (ticker, market).

Thin wrapper over the stock_reference repo so callers (extraction runner)
don't import the repo directly and the lookup policy lives in one place.
"""
from repositories.stock_reference import find_by_alias_or_ticker


def normalize(raw_symbol: str) -> tuple[str | None, str | None]:
    """Best-effort ``(ticker, market)``; ``(None, None)`` when unmatched.

    The raw string is always kept by the caller regardless of the result.
    """
    return find_by_alias_or_ticker(raw_symbol)
