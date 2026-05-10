"""Stock Dashboard FastAPI application."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Bootstrap: import db first so its re-exports (from repositories.*) finish
# before route modules trigger partial-loading of the same packages.
import db  # noqa: F401

from api.routes import (
    indicators, stocks, fundamentals, news, futures, me,
    strategies, foreign_futures,
)
from core.errors import (
    AuthError, FetcherError, RepositoryError, StockDashboardError,
)
from core.settings import settings

logger = logging.getLogger(__name__)

app = FastAPI(title="Stock Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*"],
)

app.include_router(indicators.router)
app.include_router(stocks.router)
app.include_router(fundamentals.router)
app.include_router(news.router)
app.include_router(futures.router)
app.include_router(foreign_futures.router)
app.include_router(me.router)
app.include_router(strategies.router)


_ERROR_TO_STATUS: list[tuple[type[StockDashboardError], int]] = [
    (AuthError, 401),
    (FetcherError, 502),
    (RepositoryError, 500),
]


@app.exception_handler(StockDashboardError)
async def stock_dashboard_error_handler(request: Request, exc: StockDashboardError):
    status = 500
    for cls, code in _ERROR_TO_STATUS:
        if isinstance(exc, cls):
            status = code
            break
    detail = (
        "資料來源暫時無法取得"
        if isinstance(exc, FetcherError)
        else (str(exc) or exc.__class__.__name__)
    )
    logger.warning("api_domain_error class=%s status=%d", exc.__class__.__name__, status)
    return JSONResponse(status_code=status, content={"detail": detail})


@app.on_event("startup")
def startup():
    from core.logging import setup_logging
    setup_logging()
    from db import init_db
    init_db()
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except ImportError:
        logger.warning("scheduler_not_available")
