"""SEC company_tickers.json helper.

The US analogue of FinMind's TW stock list: SEC's full ticker→company-name
roster for every filer. SEC's fair-access policy requires a declared
``User-Agent`` header or it returns 403. The single network call lives here
so the sync logic can be unit-tested with a stubbed roster.
"""
import requests

URL = "https://www.sec.gov/files/company_tickers.json"
_USER_AGENT = "publixia-stock-tracker (https://stock.paul-learning.dev)"


def fetch_company_tickers() -> list[dict]:
    """Return ``[{"cik_str": ..., "ticker": ..., "title": ...}, ...]``.

    SEC returns a dict keyed by row index (``{"0": {...}, "1": {...}}``);
    this flattens it to a list. Transport errors propagate as the underlying
    ``requests`` exception.
    """
    r = requests.get(URL, headers={"User-Agent": _USER_AGENT}, timeout=20)
    r.raise_for_status()
    payload = r.json()
    return list(payload.values()) if isinstance(payload, dict) else []
