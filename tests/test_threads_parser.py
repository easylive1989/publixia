"""Threads post extraction from embedded data-sjs JSON (offline)."""
from scrapers.threads import _posts_from_html

# Minimal Threads-shaped page: a data-sjs script carrying one post object
# with the same key shape Threads uses (code / caption.text / taken_at).
_FIXTURE = """
<html><body>
<script type="application/json" data-sjs>
{"require":[["ScheduledServerJS","handle",null,[{"__bbox":{"result":{"data":
{"thread_items":[{"post":{"code":"DZGyiJ3kw","pk":"123","taken_at":1780451794,
"caption":{"text":"家父持股緯創全數售出，僅留一張"}}}]}}}}]]]}
</script>
<script type="application/json" data-sjs>
{"locale":"zh_TW","other":{"code":"en_US"}}
</script>
</body></html>
"""


def test_extracts_post_fields():
    posts = _posts_from_html(_FIXTURE)
    assert "DZGyiJ3kw" in posts
    p = posts["DZGyiJ3kw"]
    assert p.content == "家父持股緯創全數售出，僅留一張"
    assert p.posted_at == "2026-06-03T01:56:34"  # epoch 1780451794 in UTC


def test_ignores_non_post_objects():
    # the en_US 'code' has no caption text → not treated as a post
    posts = _posts_from_html(_FIXTURE)
    assert "en_US" not in posts


def test_handles_garbage_gracefully():
    assert _posts_from_html("<html>no scripts</html>") == {}
    assert _posts_from_html("") == {}
