"""Groq Whisper client: auth header, model/language payload, error handling."""
import pytest

import core.groq_ai as groq_ai
from core.groq_ai import GroqAIError
from core.settings import settings


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {"text": "轉錄文字"}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            err = requests.HTTPError()
            err.response = self
            raise err


def test_unconfigured_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "groq_api_key", None)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    with pytest.raises(GroqAIError):
        groq_ai.transcribe(str(audio))


def test_sends_auth_model_language(monkeypatch, tmp_path):
    from pydantic import SecretStr
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("sk-test"))
    monkeypatch.setattr(settings, "groq_stt_model", "whisper-large-v3")
    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        captured["has_file"] = "file" in (files or {})
        return _Resp(payload={"text": "台積電很強"})

    monkeypatch.setattr(groq_ai.requests, "post", fake_post)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio-bytes")

    text = groq_ai.transcribe(str(audio), language="zh")

    assert text == "台積電很強"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["data"]["model"] == "whisper-large-v3"
    assert captured["data"]["language"] == "zh"
    assert captured["has_file"]


def test_http_error_wrapped(monkeypatch, tmp_path):
    from pydantic import SecretStr
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("sk-test"))
    monkeypatch.setattr(groq_ai.requests, "post",
                        lambda *a, **k: _Resp(status=429))
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    with pytest.raises(GroqAIError):
        groq_ai.transcribe(str(audio))
