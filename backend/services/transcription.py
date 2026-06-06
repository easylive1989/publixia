"""Turn a podcast episode into a plain-text transcript.

Two paths, cheapest first:

1. **RSS transcript** — if the feed supplied a ``<podcast:transcript>`` URL we
   fetch it and strip VTT/SRT/JSON down to plain text. Free and instant.
2. **Groq Whisper** — otherwise download the audio, transcode to 16 kHz mono
   with ffmpeg (shrinks it under Groq's 25 MB cap; Whisper downsamples to 16 kHz
   internally anyway, so no accuracy loss), chunk by time only if still too big,
   and transcribe each chunk.

``transcribe_post`` returns ``(text, source)`` where source is ``'rss'`` or
``'groq'`` (stored on the post for observability).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile

import requests

from core import groq_ai
from core.chinese import to_traditional

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = 120
_FETCH_TIMEOUT = 60
# Stay safely under Groq's 25 MB request cap. Decimal 24 MB leaves margin
# regardless of whether Groq means 25 MB (decimal) or 25 MiB.
_MAX_CHUNK_BYTES = 24 * 1000 * 1000
_CHUNK_SECONDS = 1200  # 20-minute chunks when an episode is still too large
# A Traditional-Chinese sample to bias Whisper away from Simplified output
# (OpenCC is the guarantee; this just reduces the conversion it has to do).
_ZH_TW_PROMPT = "以下是繁體中文的內容。"

_CUE_TIMESTAMP_RE = re.compile(r"-->")


class TranscriptionError(RuntimeError):
    """Raised when neither transcript path can produce text."""


# --- RSS transcript path -------------------------------------------------

def _cues_to_text(raw: str) -> str:
    """Strip VTT/SRT markup to plain text: drop the WEBVTT header, cue index
    lines, timestamp lines, and blank lines; keep the spoken text."""
    out = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s == "WEBVTT" or s.isdigit() or _CUE_TIMESTAMP_RE.search(s):
            continue
        out.append(s)
    return " ".join(out)


def _json_to_text(raw: str) -> str:
    """Podcasting-2.0 JSON transcript → plain text (segments[].body/text)."""
    import json
    data = json.loads(raw)
    segments = data.get("segments", []) if isinstance(data, dict) else []
    parts = [seg.get("body") or seg.get("text") or "" for seg in segments]
    return " ".join(p.strip() for p in parts if p).strip()


def _fetch_transcript(url: str) -> str:
    resp = requests.get(url, timeout=_FETCH_TIMEOUT)
    resp.raise_for_status()
    raw = resp.text.strip()
    if raw.startswith("WEBVTT") or _CUE_TIMESTAMP_RE.search(raw):
        return _cues_to_text(raw)
    if raw[:1] in "{[":
        return _json_to_text(raw)
    return raw


# --- Groq audio path -----------------------------------------------------

def _download(url: str, dest: str) -> None:
    with requests.get(url, stream=True, timeout=_DOWNLOAD_TIMEOUT) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                fh.write(chunk)


def _transcode(src: str, dst: str) -> None:
    """Downmix to 16 kHz mono MP3 (~0.5 MB/min) to shrink under the size cap."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1",
         "-c:a", "libmp3lame", "-b:a", "64k", dst],
        check=True, capture_output=True,
    )


def _chunk(src: str, workdir: str) -> list[str]:
    """Split into time-based chunks; returns chunk paths in order."""
    pattern = os.path.join(workdir, "chunk_%03d.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-f", "segment",
         "-segment_time", str(_CHUNK_SECONDS), "-c", "copy", pattern],
        check=True, capture_output=True,
    )
    return sorted(
        os.path.join(workdir, f) for f in os.listdir(workdir)
        if f.startswith("chunk_")
    )


def _transcribe_audio(audio_url: str, prompt: str | None = None) -> str:
    if not shutil.which("ffmpeg"):
        raise TranscriptionError("ffmpeg not available")
    with tempfile.TemporaryDirectory() as workdir:
        raw_path = os.path.join(workdir, "raw")
        _download(audio_url, raw_path)
        small_path = os.path.join(workdir, "small.mp3")
        _transcode(raw_path, small_path)

        if os.path.getsize(small_path) <= _MAX_CHUNK_BYTES:
            parts = [small_path]
        else:
            parts = _chunk(small_path, workdir)

        texts = [groq_ai.transcribe(p, prompt=prompt or _ZH_TW_PROMPT) for p in parts]
        return "\n".join(t for t in texts if t).strip()


# --- Orchestrator --------------------------------------------------------

def transcribe_post(
    audio_url: str | None,
    transcript_url: str | None,
    prompt: str | None = None,
) -> tuple[str, str]:
    """Return ``(transcript_text, source)``, always in Traditional Chinese.
    Tries the RSS transcript first, then Groq. ``prompt`` is a per-podcast Whisper
    context hint (correct show/host/term spellings) to curb proper-noun errors.
    Raises ``TranscriptionError`` if neither path yields text."""
    if transcript_url:
        try:
            text = _fetch_transcript(transcript_url)
            if text:
                return to_traditional(text), "rss"
            logger.warning("transcript_rss_empty url=%s", transcript_url)
        except Exception:  # noqa: BLE001 — fall back to audio transcription
            logger.warning("transcript_rss_failed url=%s", transcript_url, exc_info=True)

    if audio_url:
        text = _transcribe_audio(audio_url, prompt=prompt)
        if text:
            return to_traditional(text), "groq"

    raise TranscriptionError("no transcript produced")
