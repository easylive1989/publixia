"""Threads scraper.

Threads server-renders only the first few posts as inline ``data-sjs`` JSON;
older posts arrive via ``/graphql/query`` XHR as you scroll. So we drive a
stealth browser, scroll to lazy-load history, and parse posts from BOTH the
inline JSON and the captured GraphQL responses. Each post object carries a
``code`` (shortcode), ``caption.text``, and ``taken_at`` (epoch seconds).

Logged-out works for these public profiles (verified by the Phase 0 spike).
``account['session_cookie']`` is accepted for the future case where a profile
gets gated, but is not required today.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from scrapling.fetchers import StealthyFetcher

from scrapers.base import ScrapedPost, epoch_to_iso, iter_dicts

logger = logging.getLogger(__name__)

_SCRIPT_JSON_RE = re.compile(
    r'<script type="application/json"[^>]*>(.*?)</script>', re.DOTALL
)
# Cap scroll iterations so a never-ending feed (or a login banner that keeps
# the page tall) can't loop forever. Scaled by the requested backfill window.
_SCROLLS_PER_MONTH = 8
_MAX_SCROLLS = 40
# Incremental (steady-state) runs only need the newest posts: scroll shallow
# and stop as soon as we scroll into already-seen territory.
_INCREMENTAL_MAX_SCROLLS = 6
_EARLY_STOP_KNOWN = 5

_POST_CODE_RE = re.compile(r"/post/([^/?#]+)")


def _post_url(handle: str, code: str) -> str:
    return f"https://www.threads.com/@{handle}/post/{code}"


def _code_from_href(href: str | None) -> str | None:
    if not href:
        return None
    m = _POST_CODE_RE.search(href)
    return m.group(1) if m else None


def _posts_from_json(data) -> dict[str, ScrapedPost]:
    """Pull post-shaped dicts (code + caption.text) out of any decoded JSON."""
    found: dict[str, ScrapedPost] = {}
    for obj in iter_dicts(data):
        code = obj.get("code")
        if not isinstance(code, str):
            continue
        caption = obj.get("caption")
        text = caption.get("text") if isinstance(caption, dict) else None
        if not text:
            continue
        posted_at = epoch_to_iso(obj.get("taken_at"))
        # handle is filled in by the caller (not present on the post object)
        found.setdefault(
            code,
            ScrapedPost(
                platform_post_id=code, url="", content=text, posted_at=posted_at
            ),
        )
    return found


def _posts_from_html(html: str) -> dict[str, ScrapedPost]:
    out: dict[str, ScrapedPost] = {}
    for blob in _SCRIPT_JSON_RE.findall(html or ""):
        try:
            data = json.loads(blob)
        except (ValueError, TypeError):
            continue
        for code, post in _posts_from_json(data).items():
            out.setdefault(code, post)
    return out


def _posts_from_xhr(captured) -> dict[str, ScrapedPost]:
    out: dict[str, ScrapedPost] = {}
    for resp in captured or []:
        data = None
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001 — fall back to raw body
            try:
                data = json.loads(resp.body)
            except Exception:  # noqa: BLE001
                continue
        for code, post in _posts_from_json(data).items():
            out.setdefault(code, post)
    return out


def _make_scroller(max_scrolls: int, known_ids: frozenset[str]):
    """Return a sync page_action that scrolls to lazy-load posts.

    Stops when the feed stops growing, the scroll cap is hit, or — for
    incremental runs — we've scrolled into already-seen territory (≥
    ``_EARLY_STOP_KNOWN`` already-stored posts are on screen), so steady-state
    runs don't re-scroll the whole backfill window every time.
    """

    def scroll(page):
        last_height = 0
        stagnant = 0
        for _ in range(max_scrolls):
            page.mouse.wheel(0, 30000)
            page.wait_for_timeout(1800)

            if known_ids:
                try:
                    hrefs = page.eval_on_selector_all(
                        "a[href*='/post/']",
                        "els => els.map(e => e.getAttribute('href'))",
                    )
                    visible = {_code_from_href(h) for h in hrefs}
                    visible.discard(None)
                    if len(visible & known_ids) >= _EARLY_STOP_KNOWN:
                        break
                except Exception:  # noqa: BLE001 — selector hiccup → keep scrolling
                    pass

            try:
                height = page.evaluate("document.body.scrollHeight")
            except Exception:  # noqa: BLE001
                break
            if height <= last_height:
                stagnant += 1
                if stagnant >= 2:
                    break
            else:
                stagnant = 0
            last_height = height

    return scroll


class ThreadsScraper:
    platform = "threads"

    def fetch_recent(
        self,
        account: dict,
        months: int,
        known_ids: frozenset[str] = frozenset(),
    ) -> list[ScrapedPost]:
        """Scrape recent posts.

        ``known_ids`` = post ids already stored for this account. When non-empty
        the run is treated as *incremental*: scroll shallow and stop early once
        already-seen posts come into view, instead of re-scrolling the whole
        backfill window. An empty set means first-time backfill (deep scroll).
        The ``months`` cutoff still applies in both modes.
        """
        handle = account["handle"]
        url = account.get("profile_url") or f"https://www.threads.com/@{handle}"
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=30 * max(months, 1))
        ).strftime("%Y-%m-%dT%H:%M:%S")
        incremental = bool(known_ids)
        max_scrolls = (
            _INCREMENTAL_MAX_SCROLLS
            if incremental
            else min(_SCROLLS_PER_MONTH * max(months, 1), _MAX_SCROLLS)
        )

        cookies = None
        if account.get("session_cookie"):
            try:
                cookies = json.loads(account["session_cookie"])
            except (ValueError, TypeError):
                logger.warning("threads_bad_session_cookie handle=%s", handle)

        fetch_kwargs = dict(
            headless=True,
            network_idle=True,
            block_ads=True,
            capture_xhr="graphql",
            page_action=_make_scroller(max_scrolls, known_ids),
            timeout=120000,
        )
        if cookies:
            fetch_kwargs["cookies"] = cookies

        resp = StealthyFetcher.fetch(url, **fetch_kwargs)

        posts = _posts_from_html(resp.html_content)
        for code, post in _posts_from_xhr(getattr(resp, "captured_xhr", None)).items():
            posts.setdefault(code, post)

        result = []
        for code, post in posts.items():
            post.url = _post_url(handle, code)
            # keep posts with unknown timestamps (rare); drop ones older than cutoff
            if post.posted_at is None or post.posted_at >= cutoff:
                result.append(post)

        result.sort(key=lambda p: p.posted_at or "", reverse=True)
        logger.info(
            "threads_scraped handle=%s mode=%s scraped=%d kept=%d months=%d",
            handle, "incremental" if incremental else "backfill",
            len(posts), len(result), months,
        )
        return result
