"""Transcription service: RSS-first, Groq fallback, VTT/SRT/JSON stripping."""
import pytest

import services.transcription as tx


class _Resp:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError()


# --- cue / json stripping (pure) ---

def test_vtt_stripped_to_text():
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n今天聊台積電\n\n2\n00:00:03.000 --> 00:00:05.000\n我加碼了\n"
    assert tx._cues_to_text(vtt) == "今天聊台積電 我加碼了"


def test_srt_stripped_to_text():
    srt = "1\n00:00:01,000 --> 00:00:03,000\n聊聊長榮\n\n2\n00:00:03,000 --> 00:00:05,000\n我賣掉了\n"
    assert tx._cues_to_text(srt) == "聊聊長榮 我賣掉了"


def test_json_transcript_to_text():
    raw = '{"segments":[{"body":"買進聯發科"},{"text":"看多輝達"}]}'
    assert tx._json_to_text(raw) == "買進聯發科 看多輝達"


# --- orchestrator ---

def test_rss_path_preferred_skips_groq(monkeypatch):
    monkeypatch.setattr(tx.requests, "get",
                        lambda url, timeout=None: _Resp(text="WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\n台積電\n"))
    called = {"groq": False}
    monkeypatch.setattr(tx, "_transcribe_audio",
                        lambda *a, **k: called.__setitem__("groq", True) or "x")

    text, source = tx.transcribe_post("https://cdn/ep.mp3", "https://cdn/ep.vtt")
    assert source == "rss"
    assert text == "台積電"
    assert called["groq"] is False


def test_falls_back_to_groq_when_no_transcript_url(monkeypatch):
    monkeypatch.setattr(tx, "_transcribe_audio", lambda url: "Whisper 轉出的逐字稿")
    text, source = tx.transcribe_post("https://cdn/ep.mp3", None)
    assert source == "groq"
    assert text == "Whisper 轉出的逐字稿"


def test_falls_back_to_groq_when_rss_fetch_fails(monkeypatch):
    monkeypatch.setattr(tx.requests, "get",
                        lambda url, timeout=None: _Resp(status=500))
    monkeypatch.setattr(tx, "_transcribe_audio", lambda url: "後援逐字稿")
    text, source = tx.transcribe_post("https://cdn/ep.mp3", "https://cdn/bad.vtt")
    assert source == "groq"
    assert text == "後援逐字稿"


def test_raises_when_nothing_available(monkeypatch):
    with pytest.raises(tx.TranscriptionError):
        tx.transcribe_post(None, None)


def test_audio_path_transcodes_chunks_and_joins(monkeypatch, tmp_path):
    # ffmpeg present; small file (no chunking); two no-op subprocess calls.
    monkeypatch.setattr(tx.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(tx, "_download", lambda url, dest: open(dest, "wb").close())

    def fake_transcode(src, dst):
        open(dst, "wb").write(b"x")  # tiny → under cap → single chunk
    monkeypatch.setattr(tx, "_transcode", fake_transcode)
    monkeypatch.setattr(tx.groq_ai, "transcribe", lambda p, prompt=None: "整段逐字稿")

    text = tx._transcribe_audio("https://cdn/ep.mp3")
    assert text == "整段逐字稿"


def test_audio_path_missing_ffmpeg_raises(monkeypatch):
    monkeypatch.setattr(tx.shutil, "which", lambda _: None)
    with pytest.raises(tx.TranscriptionError):
        tx._transcribe_audio("https://cdn/ep.mp3")


def test_groq_output_converted_to_traditional(monkeypatch):
    # Whisper returns Simplified; transcribe_post must return Traditional.
    monkeypatch.setattr(tx, "_transcribe_audio",
                        lambda url: "欢迎收听股癌,本集节目由软件赞助")
    text, source = tx.transcribe_post("https://cdn/ep.mp3", None)
    assert source == "groq"
    assert text == "歡迎收聽股癌,本集節目由軟體贊助"


def test_rss_output_converted_to_traditional(monkeypatch):
    monkeypatch.setattr(tx.requests, "get",
                        lambda url, timeout=None: _Resp(text="收听简体内容"))
    text, source = tx.transcribe_post("https://cdn/ep.mp3", "https://cdn/ep.txt")
    assert source == "rss"
    assert text == "收聽簡體內容"
