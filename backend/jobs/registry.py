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

from services.intraday_heat import run_intraday_heat_signal
from services.institutional_flow_sync import run_institutional_flow_sync
from services.market_volume_sync import run_market_volume_sync
from services.backup import backup_db_to_r2


@dataclass(frozen=True)
class JobSpec:
    fn: Callable[[], object]
    default_cron: str
    description: str


JOBS: dict[str, JobSpec] = {
    "intraday_heat_signal": JobSpec(run_intraday_heat_signal, "0 13 * * 1-5", "盤中大盤冷熱判讀推 Discord"),
    "market_volume_sync": JobSpec(run_market_volume_sync, "0 16 * * 1-5", "同步 TWSE 大盤成交金額供冷熱判讀"),
    "institutional_flow_sync": JobSpec(run_institutional_flow_sync, "0 20 * * 1-5", "同步 TWSE 三大法人最終買賣金額"),
    "backup_db":       JobSpec(backup_db_to_r2,           "0 3 * * *",    "DB 備份至 Cloudflare R2"),
}
