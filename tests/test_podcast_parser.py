"""PodcastScraper RSS parsing (no network — feeds a static RSS string).

Covers: GUID→platform_post_id, audio enclosure, the Podcasting-2.0 transcript
tag (present and absent), title, pubDate→naive-UTC ISO, and that non-episode
items (no audio, no transcript) are dropped.
"""
import feedparser

from scrapers.podcast import _posts_from_feed

_RSS = """<?xml version="1.0"?>
<rss version="2.0" xmlns:podcast="https://podcastindex.org/namespace/1.0">
<channel>
  <title>投資 Podcast</title>
  <item>
    <title>第一集 台積電</title>
    <guid isPermaLink="false">GUID-001</guid>
    <link>https://show.example/ep1</link>
    <pubDate>Mon, 01 Jun 2026 08:00:00 +0000</pubDate>
    <enclosure url="https://cdn.example/ep1.mp3" length="1000" type="audio/mpeg"/>
    <podcast:transcript url="https://cdn.example/ep1.vtt" type="text/vtt"/>
  </item>
  <item>
    <title>第二集 沒有逐字稿</title>
    <guid>GUID-002</guid>
    <link>https://show.example/ep2</link>
    <pubDate>Tue, 02 Jun 2026 08:00:00 +0000</pubDate>
    <enclosure url="https://cdn.example/ep2.mp3" length="2000" type="audio/mpeg"/>
  </item>
  <item>
    <title>純文字公告（非單集）</title>
    <guid>GUID-003</guid>
    <link>https://show.example/note</link>
    <pubDate>Wed, 03 Jun 2026 08:00:00 +0000</pubDate>
  </item>
</channel>
</rss>"""


def _posts():
    return _posts_from_feed(feedparser.parse(_RSS))


def test_drops_non_episode_items():
    ids = {p.platform_post_id for p in _posts()}
    assert ids == {"GUID-001", "GUID-002"}  # GUID-003 has no audio/transcript


def test_episode_with_transcript():
    p = next(p for p in _posts() if p.platform_post_id == "GUID-001")
    assert p.title == "第一集 台積電"
    assert p.url == "https://show.example/ep1"
    assert p.audio_url == "https://cdn.example/ep1.mp3"
    assert p.transcript_url == "https://cdn.example/ep1.vtt"
    assert p.content == ""
    assert p.posted_at == "2026-06-01T08:00:00"  # naive-UTC ISO


def test_episode_without_transcript():
    p = next(p for p in _posts() if p.platform_post_id == "GUID-002")
    assert p.audio_url == "https://cdn.example/ep2.mp3"
    assert p.transcript_url is None


def test_sorted_newest_first():
    posts = _posts()
    assert [p.platform_post_id for p in posts] == ["GUID-002", "GUID-001"]
