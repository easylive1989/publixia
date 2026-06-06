"""Simplified → Traditional Chinese conversion.

Whisper (incl. Groq's whisper-large-v3) transcribes Mandarin to *Simplified*
regardless of the source, so podcast transcripts come back simplified. We
convert to Traditional with OpenCC ``s2twp`` (Simplified → Traditional, Taiwan
standard + localised phrasing, e.g. 软件→軟體). Conversion is idempotent on
already-Traditional text, so it's safe to apply unconditionally.
"""
import logging

logger = logging.getLogger(__name__)

try:
    import opencc
    _CONVERTER = opencc.OpenCC("s2twp")
except Exception:  # noqa: BLE001 — degrade gracefully if opencc is unavailable
    _CONVERTER = None
    logger.warning("opencc_unavailable simplified_to_traditional_disabled")


def to_traditional(text: str) -> str:
    """Convert Simplified Chinese to Taiwan-standard Traditional. Returns the
    input unchanged if it's empty or opencc isn't installed.

    ``s2twp`` normalises 台→臺 (e.g. 台積電→臺積電), but FinMind's stock roster —
    and everyday Taiwanese finance/media — use 台, so we map 臺→台 back. This
    keeps extracted symbols matching ``stock_reference`` (otherwise 臺積電 would
    fail to normalise) and reads more naturally.
    """
    if not text or _CONVERTER is None:
        return text
    return _CONVERTER.convert(text).replace("臺", "台")
