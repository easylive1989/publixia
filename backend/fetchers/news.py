"""新聞 fetcher — 從 RSS 抓取財經新聞，快取在記憶體。"""
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

FEEDS = [
    ("鉅亨網台股", "https://news.cnyes.com/rss/v1/news/category/tw_stock"),
    ("鉅亨頭條",   "https://news.cnyes.com/rss/v1/news/category/headline"),
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
CACHE_TTL = 1800  # 30 分鐘

_cache: list[dict] = []
_cache_time: datetime | None = None


def fetch_news() -> list[dict]:
    global _cache, _cache_time
    items = []
    for source, url in FEEDS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_str = item.findtext("pubDate") or ""
                if not title or not link:
                    continue
                try:
                    pub_dt = parsedate_to_datetime(pub_str)
                    published = pub_dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    published = ""
                items.append({
                    "title": title,
                    "url": link,
                    "source": source,
                    "published": published,
                })
        except Exception as e:
            print(f"[news] {source}: {e}")

    items.sort(key=lambda x: x.get("published", ""), reverse=True)
    _cache = items[:30]
    _cache_time = datetime.now()
    print(f"[news] 更新完成，共 {len(_cache)} 則")
    return _cache


def get_cached_news() -> list[dict]:
    if not _cache or _cache_time is None or (datetime.now() - _cache_time).seconds > CACHE_TTL:
        return fetch_news()
    return _cache
