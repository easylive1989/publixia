"""Cloudflare Workers AI REST helper.

Calls the Workers AI inference API directly from the backend (no separate
Worker). Used to extract structured buy/sell signals from post text.

    POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}
    Authorization: Bearer {api_token}
"""
import json
import logging

import requests

from core.settings import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.cloudflare.com/client/v4/accounts"


class CloudflareAIError(RuntimeError):
    """Raised when Workers AI is unconfigured or returns a non-OK response."""


def run_ai(
    system: str,
    user: str,
    json_schema: dict | None = None,
    model: str | None = None,
    timeout: int = 60,
) -> dict | str:
    """Run one chat completion. Returns the model output.

    With ``json_schema`` the call requests JSON mode and the return value is
    the parsed object (dict). Without it, the raw text response (str) is
    returned. Raises ``CloudflareAIError`` on misconfig / API failure.
    """
    if not settings.cf_account_id or not settings.cf_api_token:
        raise CloudflareAIError("Cloudflare Workers AI not configured (cf_account_id / cf_api_token)")

    model = model or settings.cf_ai_model
    url = f"{_BASE}/{settings.cf_account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {settings.cf_api_token.get_secret_value()}",
        "Content-Type": "application/json",
    }
    body: dict = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    }
    if json_schema is not None:
        body["response_format"] = {"type": "json_schema", "json_schema": json_schema}

    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success", False):
        raise CloudflareAIError(f"Workers AI error: {payload.get('errors') or payload}")

    result = payload.get("result", {})
    response = result.get("response") if isinstance(result, dict) else None
    if response is None:
        response = result  # some models return the object at result directly

    if json_schema is None:
        return response if isinstance(response, str) else json.dumps(response)

    # JSON mode: response may already be a dict, or a JSON string.
    if isinstance(response, (dict, list)):
        return response
    try:
        return json.loads(response)
    except (ValueError, TypeError) as e:
        raise CloudflareAIError(f"Workers AI returned non-JSON in JSON mode: {response!r}") from e
