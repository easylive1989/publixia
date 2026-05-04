"""News feed routes."""
from fastapi import APIRouter, Depends

from api.dependencies import require_token

router = APIRouter(prefix="/api", tags=["news"], dependencies=[Depends(require_token)])


@router.get("/news")
def get_news(limit: int = 15):
    from fetchers.news import get_cached_news
    return get_cached_news()[:limit]
