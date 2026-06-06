"""Shared scraper types + helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ScrapedPost:
    """One scraped post, normalized across platforms.

    ``platform_post_id`` is the platform-native id (Threads shortcode);
    ``posted_at`` is a naive-UTC ISO string (``YYYY-MM-DDTHH:MM:SS``) so it
    sorts lexically, or ``None`` when the timestamp is unknown.

    The trailing fields are podcast-only and default to ``None`` so text
    platforms (Threads) build a ``ScrapedPost`` unchanged: ``audio_url`` is the
    episode's audio enclosure to transcribe, ``transcript_url`` an RSS-supplied
    transcript (Podcasting 2.0) used in preference to transcribing, and
    ``title`` the episode title (Threads posts have none).
    """
    platform_post_id: str
    url: str
    content: str
    posted_at: str | None
    audio_url: str | None = None
    transcript_url: str | None = None
    title: str | None = None


def iter_dicts(node):
    """Depth-first walk yielding every dict in a decoded-JSON structure."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from iter_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_dicts(v)


def epoch_to_iso(value) -> str | None:
    """Convert a plausible epoch-seconds value to a naive-UTC ISO string.

    Returns ``None`` for missing/implausible inputs (guards against
    millisecond/microsecond fields sneaking in as 'taken_at').
    """
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    # plausible seconds-since-epoch window: 2001-09 .. 2286
    if not (1_000_000_000 <= ts <= 9_999_999_999):
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
