"""Logging setup. Call `setup_logging()` once at startup."""
import logging
from core.settings import settings


def setup_logging() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,  # override anything FastAPI / uvicorn already set
    )
    # Suppress noisy third-party loggers per CONVENTIONS.md §4.2.
    for noisy in ("urllib3", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
