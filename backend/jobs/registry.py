"""Central registry of scheduled jobs.

Single source of truth for job name → callable + default cron expression.
The scheduler seeds `scheduler_jobs` from this dict on startup (insert-if-
missing) and then reads the row back to decide whether to wire the job up
and at what cadence.

All cron expressions are 5-field POSIX style (minute hour dom month dow)
and interpreted in the scheduler's timezone (Asia/Taipei).
"""
from collections.abc import Callable
from dataclasses import dataclass

from scrapers.runner import scrape_all_enabled
from services.extraction_runner import run_extraction
from services.stock_reference_sync import run_stock_reference_sync
from services.backup import backup_db_to_r2


@dataclass(frozen=True)
class JobSpec:
    fn: Callable[[], object]
    default_cron: str
    description: str


JOBS: dict[str, JobSpec] = {
    "scrape_accounts": JobSpec(scrape_all_enabled,        "*/30 * * * *", "抓取追蹤帳號新貼文"),
    "extract_trades":  JobSpec(run_extraction,            "5,35 * * * *", "AI 解析貼文買賣訊號"),
    "stock_ref_sync":  JobSpec(run_stock_reference_sync,  "0 7 * * *",    "同步台股/美股代號對照表"),
    "backup_db":       JobSpec(backup_db_to_r2,           "0 3 * * *",    "DB 備份至 Cloudflare R2"),
}
