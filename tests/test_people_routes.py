"""People API routes over an in-memory DB."""
from fastapi.testclient import TestClient

import main
from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo
from repositories import trades as trades_repo

client = TestClient(main.app)


def _seed_post_with_trade():
    acc = accounts_repo.list_accounts()[0]  # 爸逆逆, seeded by migration 0024
    pid, _ = posts_repo.upsert_post(
        acc["id"], "threads", "P1", "https://t/p/P1",
        "家父持股緯創全數售出", "2026-06-03T10:00:00",
    )
    trades_repo.save_trades(
        pid,
        [{"raw_symbol": "緯創", "ticker": "3231", "market": "TW", "direction": "sell", "confidence": 0.9}],
        model="m", prompt_version="v1",
    )
    posts_repo.set_extraction_status(pid, "done")
    return acc


def test_list_people_shape():
    _seed_post_with_trade()
    r = client.get("/api/people")
    assert r.status_code == 200
    people = r.json()["people"]
    dad = next(p for p in people if p["person_key"] == "dadnini")
    assert dad["display_name"] == "爸逆逆"
    assert dad["platforms"] == ["threads"]
    assert dad["trade_count"] == 1


def test_person_profile():
    r = client.get("/api/people/dadnini")
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "爸逆逆"
    assert body["accounts"][0]["handle"] == "ajhsu0820"


def test_person_posts_with_nested_trades():
    _seed_post_with_trade()
    r = client.get("/api/people/dadnini/posts")
    assert r.status_code == 200
    posts = r.json()["posts"]
    assert len(posts) == 1
    assert posts[0]["content"] == "家父持股緯創全數售出"
    assert posts[0]["trades"][0]["ticker"] == "3231"
    assert posts[0]["trades"][0]["direction"] == "sell"


def test_podcast_post_carries_title(monkeypatch):
    acc = accounts_repo.list_accounts()[0]
    pid, _ = posts_repo.upsert_post(
        acc["id"], "podcast", "EP1", "https://show/ep1", "",
        "2026-06-05T10:00:00", audio_url="https://cdn/ep1.mp3", title="第一集：台積電",
    )
    posts_repo.set_post_transcript(pid, "完整逐字稿", "groq")

    r = client.get("/api/people/dadnini/posts")
    assert r.status_code == 200
    ep = next(p for p in r.json()["posts"] if p["platform_post_id"] == "EP1")
    assert ep["title"] == "第一集：台積電"
    assert ep["platform"] == "podcast"

    # threads posts have a null title (no episode title)
    r2 = client.get("/api/timeline")
    assert all("title" in p for p in r2.json()["posts"])


def test_unknown_person_404():
    assert client.get("/api/people/ghost").status_code == 404
    assert client.get("/api/people/ghost/posts").status_code == 404


def test_timeline_merges_people_with_author_and_trades():
    accts = accounts_repo.list_accounts()
    # one post per person, different times
    pid_dad, _ = posts_repo.upsert_post(
        accts[0]["id"], "threads", "D1", "https://t/p/D1", "家父賣出緯創", "2026-06-03T10:00:00"
    )
    trades_repo.save_trades(
        pid_dad,
        [{"raw_symbol": "緯創", "ticker": "3231", "market": "TW", "direction": "sell", "confidence": 0.9}],
        model="m", prompt_version="v1",
    )
    posts_repo.upsert_post(
        accts[1]["id"], "threads", "B1", "https://t/p/B1", "放棄吧散戶", "2026-06-04T10:00:00"
    )

    r = client.get("/api/timeline")
    assert r.status_code == 200
    posts = r.json()["posts"]
    # newest first across people
    assert [p["platform_post_id"] for p in posts] == ["B1", "D1"]
    assert posts[0]["person"]["display_name"] == "巴逆逆"
    assert posts[1]["person"]["person_key"] == "dadnini"
    assert posts[1]["trades"][0]["ticker"] == "3231"


def test_timeline_limit_validation():
    assert client.get("/api/timeline?limit=0").status_code == 400
    assert client.get("/api/timeline?limit=999").status_code == 400
