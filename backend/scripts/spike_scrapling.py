"""Phase 0 spike: evaluate logged-out scraping of the tracked accounts.

NOT wired into the app. Run manually:

    cd backend && .venv/bin/python scripts/spike_scrapling.py

For each target it does a logged-out stealth-browser fetch and reports:
  - HTTP status + final URL (did we get redirected to a login wall?)
  - login-wall heuristics hit
  - how many post-like nodes we can see in the rendered DOM
  - what we can pull out of Threads' embedded `data-sjs` JSON
      (post shortcode / text / timestamp)
  - dumps raw HTML + extracted JSON candidates to scripts/spike_out/ for
    manual inspection.

The output of this script is the decision gate for the rest of the rebuild:
it tells us whether logged-out reads work and which field-extraction
strategy to build the real scraper on.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from scrapling.fetchers import StealthyFetcher

OUT_DIR = Path(__file__).parent / "spike_out"
OUT_DIR.mkdir(exist_ok=True)

TARGETS = [
    ("threads_ajhsu0820", "https://www.threads.com/@ajhsu0820"),
    ("threads_banini31", "https://www.threads.com/@banini31"),
    ("facebook_DieWithoutBang", "https://www.facebook.com/DieWithoutBang"),
]

LOGIN_WALL_MARKERS = [
    "log in to threads",
    "log into facebook",
    "you must log in",
    "login_form",
    "請先登入",
    "登入 facebook",
    "log in or sign up",
    "see more on facebook",
    "see posts, photos and more",
]


def fetch(url: str):
    """Logged-out stealth fetch. Returns the Scrapling Response or raises."""
    return StealthyFetcher.fetch(
        url,
        headless=True,
        network_idle=True,
        block_ads=True,
        timeout=60000,
        wait=3000,
    )


def iter_json_objects(node):
    """Walk a decoded-JSON structure yielding every dict."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from iter_json_objects(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_json_objects(v)


def extract_threads_posts(html: str) -> list[dict]:
    """Best-effort: parse `data-sjs` JSON blobs and pull post-looking dicts.

    Threads embeds Relay payloads in <script type="application/json"
    data-sjs>...</script>. Posts carry a `code` (shortcode), some caption
    text, and `taken_at` (epoch seconds). We search every nested dict for
    that shape.
    """
    blobs = re.findall(
        r'<script type="application/json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    posts: dict[str, dict] = {}
    for blob in blobs:
        try:
            data = json.loads(blob)
        except Exception:
            continue
        for obj in iter_json_objects(data):
            code = obj.get("code") if isinstance(obj, dict) else None
            if not code:
                continue
            caption = obj.get("caption")
            text = None
            if isinstance(caption, dict):
                text = caption.get("text")
            text = text or obj.get("title")
            taken_at = obj.get("taken_at") or obj.get("device_timestamp")
            if text or taken_at:
                posts.setdefault(
                    code,
                    {
                        "code": code,
                        "text": (text or "")[:200],
                        "taken_at": taken_at,
                    },
                )
    return list(posts.values())


def analyze(name: str, url: str) -> dict:
    report: dict = {"name": name, "url": url}
    try:
        page = fetch(url)
    except Exception as e:  # noqa: BLE001
        report["error"] = f"{type(e).__name__}: {e}"
        return report

    html = page.html_content or ""
    text_all = (page.get_all_text() or "").lower()
    (OUT_DIR / f"{name}.html").write_text(html, encoding="utf-8")

    report["status"] = getattr(page, "status", None)
    report["final_url"] = getattr(page, "url", None)
    report["html_bytes"] = len(html)
    report["login_wall_markers"] = [m for m in LOGIN_WALL_MARKERS if m in text_all]

    # Generic DOM probes (counts only — selectors differ per platform).
    probes = {
        "article": len(page.css("article")),
        "a[href*='/post/']": len(page.css("a[href*='/post/']")),
        "time": len(page.css("time")),
        "img": len(page.css("img")),
        "data-sjs scripts": len(page.css("script[data-sjs]")),
    }
    report["dom_probes"] = probes

    if name.startswith("threads"):
        posts = extract_threads_posts(html)
        report["threads_json_posts_found"] = len(posts)
        report["threads_sample"] = posts[:3]
        (OUT_DIR / f"{name}_posts.json").write_text(
            json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return report


def main() -> int:
    reports = []
    for name, url in TARGETS:
        print(f"\n{'=' * 60}\nFetching {name}: {url}", flush=True)
        rep = analyze(name, url)
        reports.append(rep)
        print(json.dumps(rep, ensure_ascii=False, indent=2), flush=True)

    summary = OUT_DIR / "summary.json"
    summary.write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nArtifacts written to {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
