"""FinMind v4 /data helper.

Centralises the base URL, bearer token, and error-shape normalisation
so each fetcher can just ``from core.finmind import request``.
"""
import requests

from core.settings import settings

URL = "https://api.finmindtrade.com/api/v4/data"
_TOKEN = settings.finmind_token.get_secret_value().strip()


def request(dataset: str, start_date: str, end_date: str | None = None) -> list[dict]:
    """Fetch ``dataset`` from FinMind and return the ``data`` array.

    Raises ``RuntimeError`` when FinMind responds with a non-OK ``status``;
    transport errors propagate as the underlying ``requests`` exception.
    """
    params = {"dataset": dataset, "start_date": start_date}
    if end_date:
        params["end_date"] = end_date
    headers = {}
    if _TOKEN:
        headers["Authorization"] = f"Bearer {_TOKEN}"
    r = requests.get(URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"FinMind {dataset} error: {payload.get('msg') or payload}")
    return payload.get("data") or []
