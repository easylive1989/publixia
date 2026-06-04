"""Incremental-scrape plumbing: known-id lookup, href parsing, mode selection."""
import scrapers.threads as threads
from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo
from scrapers.base import ScrapedPost


def test_known_post_ids_returns_stored_codes():
    acc = accounts_repo.list_accounts()[0]
    assert posts_repo.known_post_ids(acc["id"]) == frozenset()
    posts_repo.upsert_post(acc["id"], "threads", "AAA", "u", "c", "2026-06-01T00:00:00")
    posts_repo.upsert_post(acc["id"], "threads", "BBB", "u", "c", "2026-06-02T00:00:00")
    assert posts_repo.known_post_ids(acc["id"]) == frozenset({"AAA", "BBB"})


def test_code_from_href():
    assert threads._code_from_href("/@h/post/DZ123") == "DZ123"
    assert threads._code_from_href("https://www.threads.com/@h/post/DZ9?x=1") == "DZ9"
    assert threads._code_from_href("/@h/followers") is None
    assert threads._code_from_href(None) is None


class _FakeResp:
    def __init__(self, html):
        self.html_content = html
        self.captured_xhr = []


_FIXTURE = (
    '<script type="application/json" data-sjs>'
    '{"x":{"code":"DZ1","taken_at":1780451794,"caption":{"text":"買進台積電"}}}'
    "</script>"
)


def test_fetch_recent_accepts_known_ids_and_parses(monkeypatch):
    captured = {}

    def fake_fetch(url, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeResp(_FIXTURE)

    monkeypatch.setattr(threads.StealthyFetcher, "fetch", staticmethod(fake_fetch))

    account = {"handle": "ajhsu0820", "profile_url": "https://www.threads.com/@ajhsu0820"}
    out = threads.ThreadsScraper().fetch_recent(account, months=1, known_ids=frozenset({"OLD"}))

    assert [p.platform_post_id for p in out] == ["DZ1"]
    assert out[0].url == "https://www.threads.com/@ajhsu0820/post/DZ1"
    assert isinstance(out[0], ScrapedPost)
    # incremental run requested → a page_action scroller was wired up
    assert callable(captured["kwargs"]["page_action"])
