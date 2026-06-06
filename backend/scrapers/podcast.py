"""Podcast scraper.

Podcasts are distributed as RSS feeds: one HTTP GET returns every recent
episode as an ``<item>`` with a GUID, title, ``pubDate``, an audio ``<enclosure>``,
and — for Podcasting-2.0 feeds — a ``<podcast:transcript>`` URL. So unlike the
Threads scraper there's no browser and no scrolling; we fetch the feed and map
each episode to a :class:`ScrapedPost`.

The transcript isn't inline, so ``content`` starts empty: the post is upserted
with ``transcript_status='pending'`` (because ``audio_url`` is set) and the
transcription job later fills ``content`` before extraction runs. ``transcript_url``
(when the feed provides one) lets that job skip audio transcription entirely.
"""
from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from scrapers.base import ScrapedPost, epoch_to_iso

logger = logging.getLogger(__name__)

_TIMEOUT = 30


def _audio_url(entry) -> str | None:
    """The episode's audio enclosure URL, if any."""
    for enc in entry.get("enclosures", []):
        if str(enc.get("type", "")).startswith("audio/") and enc.get("href"):
            return enc["href"]
    # Fallback: a link with rel="enclosure".
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and link.get("href"):
            return link["href"]
    return None


def _transcript_url(entry) -> str | None:
    """The Podcasting-2.0 ``<podcast:transcript>`` URL, if the feed supplies one."""
    transcript = entry.get("podcast_transcript")
    if isinstance(transcript, dict):
        return transcript.get("url")
    return None


def _entry_to_post(entry) -> ScrapedPost | None:
    """Map one RSS ``<item>`` to a ScrapedPost, or None if it isn't an episode
    (no audio and no transcript means there's nothing to analyse)."""
    audio = _audio_url(entry)
    transcript = _transcript_url(entry)
    if not audio and not transcript:
        return None

    # GUID is the stable dedupe key; fall back to the audio/link URL.
    post_id = entry.get("id") or audio or entry.get("link")
    if not post_id:
        return None

    posted_at = None
    if entry.get("published_parsed"):
        posted_at = epoch_to_iso(calendar.timegm(entry["published_parsed"]))

    return ScrapedPost(
        platform_post_id=post_id,
        url=entry.get("link") or audio or "",
        content="",  # filled by the transcription job
        posted_at=posted_at,
        audio_url=audio,
        transcript_url=transcript,
        title=entry.get("title"),
    )


def _posts_from_feed(parsed) -> list[ScrapedPost]:
    """All episodes in a parsed feed, newest first."""
    posts = [p for p in (_entry_to_post(e) for e in parsed.entries) if p]
    posts.sort(key=lambda p: p.posted_at or "", reverse=True)
    return posts


class PodcastScraper:
    platform = "podcast"

    def fetch_recent(
        self,
        account: dict,
        months: int,
        known_ids: frozenset[str] = frozenset(),
    ) -> list[ScrapedPost]:
        """Fetch the RSS feed at ``account['profile_url']`` and return episodes
        published within the ``months`` window. ``known_ids`` already-stored
        episodes are skipped (re-upsert is harmless but wasteful)."""
        feed_url = account.get("profile_url")
        if not feed_url:
            logger.warning("podcast_no_feed_url handle=%s", account.get("handle"))
            return []

        resp = requests.get(feed_url, timeout=_TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=30 * max(months, 1))
        ).strftime("%Y-%m-%dT%H:%M:%S")

        out = []
        for post in _posts_from_feed(parsed):
            if post.platform_post_id in known_ids:
                continue
            if post.posted_at and post.posted_at < cutoff:
                continue
            out.append(post)
        logger.info(
            "podcast_fetch_done handle=%s episodes=%d",
            account.get("handle"), len(out),
        )
        return out
