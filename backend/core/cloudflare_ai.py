"""Cloudflare Workers AI REST helper.

Calls the Workers AI inference API directly from the backend (no separate
Worker). Used to extract structured buy/sell signals from post text.

    POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}
    Authorization: Bearer {api_token}

Workers AI hosts many open models with uneven JSON support: some honor the
``response_format: json_schema`` field, others ignore it and wrap JSON in
prose / ``` fences, and a few reject the field with a 400. So we request the
schema when asked (helps models that support it), transparently retry without
it on a 4xx, and always parse the result tolerantly.
"""
import json
import logging
import re

import requests

from core.settings import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.cloudflare.com/client/v4/accounts"
_JSON_OBJ_RE = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


class CloudflareAIError(RuntimeError):
    """Raised when Workers AI is unconfigured or returns a non-OK response."""


def _extract_json(response):
    """Coerce a model response into a Python object.

    Accepts an already-decoded dict/list, a bare JSON string, or text with
    JSON embedded in a ```json fence or surrounded by prose.
    """
    if isinstance(response, (dict, list)):
        return response
    if not isinstance(response, str):
        raise CloudflareAIError(f"unexpected response type: {type(response).__name__}")
    text = response.strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    m = _JSON_OBJ_RE.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except (ValueError, TypeError):
            pass
    raise CloudflareAIError(f"Workers AI returned non-JSON: {text[:200]!r}")


def _post(url: str, headers: dict, body: dict, timeout: int) -> dict:
    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success", False):
        raise CloudflareAIError(f"Workers AI error: {payload.get('errors') or payload}")
    result = payload.get("result", {})
    return result


def run_ai(
    system: str,
    user: str,
    json_schema: dict | None = None,
    model: str | None = None,
    timeout: int = 60,
) -> dict | str:
    """Run one chat completion. Returns the model output.

    With ``json_schema`` the return value is the parsed object (dict/list);
    parsing is tolerant of fenced/prose-wrapped JSON. Without it, the raw text
    response (str) is returned. Raises ``CloudflareAIError`` on misconfig /
    API failure / unparseable JSON.
    """
    if not settings.cf_account_id or not settings.cf_api_token:
        raise CloudflareAIError("Cloudflare Workers AI not configured (cf_account_id / cf_api_token)")

    model = model or settings.cf_ai_model
    url = f"{_BASE}/{settings.cf_account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {settings.cf_api_token.get_secret_value()}",
        "Content-Type": "application/json",
    }
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    body: dict = {"messages": messages}
    if json_schema is not None:
        body["response_format"] = {"type": "json_schema", "json_schema": json_schema}

    try:
        result = _post(url, headers, body, timeout)
    except requests.HTTPError as e:
        # Some models reject response_format → retry once without it (the
        # prompt still asks for JSON, and parsing is tolerant).
        status = e.response.status_code if e.response is not None else None
        if json_schema is not None and status in (400, 422):
            logger.warning("workers_ai_response_format_unsupported model=%s; retrying plain", model)
            body.pop("response_format", None)
            result = _post(url, headers, body, timeout)
        else:
            raise CloudflareAIError(f"Workers AI HTTP {status}") from e

    response = result.get("response") if isinstance(result, dict) else result
    if response is None:
        response = result

    if json_schema is None:
        return response if isinstance(response, str) else json.dumps(response)
    return _extract_json(response)
