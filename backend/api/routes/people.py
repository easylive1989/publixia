"""跟單追蹤 API。

- ``GET /api/people``                     首頁人物卡片清單
- ``GET /api/people/{person_key}``        個人檔案頁 header
- ``GET /api/people/{person_key}/posts``  貼文時間軸（每篇內嵌解析出的交易）
- ``POST /api/people/{person_key}/refresh`` 手動觸發該人 scrape + extract（背景執行）
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException

from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo
from repositories import trades as trades_repo

router = APIRouter(prefix="/api", tags=["people"])


@router.get("/timeline")
def get_timeline(limit: int = 60):
    """首頁：所有追蹤對象的貼文混合成一條時間軸（新→舊），每篇標註作者
    並內嵌解析出的 ``trades``。"""
    if not (1 <= limit <= 200):
        raise HTTPException(status_code=400, detail="limit 超出範圍")
    posts = posts_repo.list_recent_posts(limit=limit)
    trade_map = trades_repo.list_trades_for_posts([p["id"] for p in posts])
    for p in posts:
        p["person"] = {
            "person_key": p.pop("person_key"),
            "display_name": p.pop("display_name"),
            "avatar_url": p.pop("avatar_url"),
        }
        p["trades"] = trade_map.get(p["id"], [])
    return {"posts": posts}


@router.get("/people")
def list_people():
    """追蹤對象清單（含平台、最新貼文時間、累計交易數），供 timeline 上方的人物列。"""
    return {"people": accounts_repo.list_people_with_stats()}


@router.get("/people/{person_key}")
def get_person(person_key: str):
    person = accounts_repo.get_person(person_key)
    if person is None:
        raise HTTPException(status_code=404, detail="找不到此追蹤對象")
    return person


@router.get("/people/{person_key}/posts")
def get_person_posts(person_key: str, limit: int = 50):
    """貼文時間軸（新→舊），每篇內嵌 ``trades``。"""
    if accounts_repo.get_person(person_key) is None:
        raise HTTPException(status_code=404, detail="找不到此追蹤對象")
    if not (1 <= limit <= 200):
        raise HTTPException(status_code=400, detail="limit 超出範圍")

    posts = posts_repo.list_posts_for_person(person_key, limit=limit)
    trade_map = trades_repo.list_trades_for_posts([p["id"] for p in posts])
    for p in posts:
        p["trades"] = trade_map.get(p["id"], [])
    return {"person_key": person_key, "posts": posts}


@router.post("/people/{person_key}/refresh")
def refresh_person(person_key: str, background_tasks: BackgroundTasks):
    """手動觸發：抓該人所有 handle 的新貼文並解析（背景執行）。"""
    person = accounts_repo.get_person(person_key)
    if person is None:
        raise HTTPException(status_code=404, detail="找不到此追蹤對象")
    background_tasks.add_task(_refresh, person_key)
    return {"status": "scheduled", "person_key": person_key}


def _refresh(person_key: str) -> None:
    from scrapers.runner import scrape_account
    from services.extraction_runner import run_extraction

    for account in accounts_repo.list_accounts(enabled_only=True):
        if account["person_key"] == person_key:
            scrape_account(account)
    run_extraction(limit=100)
