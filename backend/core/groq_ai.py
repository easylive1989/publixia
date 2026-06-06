"""Groq Whisper speech-to-text helper.

Transcribes podcast audio via Groq's OpenAI-compatible audio endpoint:

    POST https://api.groq.com/openai/v1/audio/transcriptions
    Authorization: Bearer {groq_api_key}
    multipart/form-data: file=<audio>, model=whisper-large-v3, language=zh

Groq's free tier runs ``whisper-large-v3`` (good Traditional-Chinese quality)
with a 25 MB per-request cap, so callers transcode/chunk audio before calling
here. Uses ``requests`` directly to avoid pulling in the ``groq`` SDK.
"""
import logging

import requests

from core.settings import settings

logger = logging.getLogger(__name__)

_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class GroqAIError(RuntimeError):
    """Raised when Groq is unconfigured or returns a non-OK response."""


def transcribe(audio_path: str, language: str | None = "zh", timeout: int = 300) -> str:
    """Transcribe one audio file and return its plain text.

    ``language`` is an ISO-639-1 hint (default ``zh``); pass ``None`` to let
    Whisper auto-detect. Raises ``GroqAIError`` on misconfig / API failure.
    """
    if not settings.groq_api_key:
        raise GroqAIError("Groq not configured (groq_api_key)")

    headers = {"Authorization": f"Bearer {settings.groq_api_key.get_secret_value()}"}
    data = {"model": settings.groq_stt_model, "response_format": "json"}
    if language:
        data["language"] = language

    try:
        with open(audio_path, "rb") as fh:
            resp = requests.post(
                _URL, headers=headers, data=data,
                files={"file": fh}, timeout=timeout,
            )
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        raise GroqAIError(f"Groq HTTP {status}") from e

    return resp.json().get("text", "")
