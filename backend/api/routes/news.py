"""News feed routes."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["news"])


@router.get("/news")
def get_news(limit: int = 15):
    from fetchers.news import get_cached_news
    return get_cached_news()[:limit]
