"""APScheduler bootstrap.

Schedule rows live in the `scheduler_jobs` SQLite table; the in-code
`jobs.registry.JOBS` dict provides the authoritative name → callable map
plus a default cron used the first time a new job appears.

Boot sequence:
1. For every entry in JOBS, insert a default row if missing (existing
   rows are never overwritten — they reflect admin edits).
2. Read the table back; for each enabled row whose name is in the
   registry, parse cron_expr via APScheduler's `CronTrigger.from_crontab`
   and add the job. Each invocation is wrapped to record run status.
3. Unknown rows (registry entry deleted but DB row remains) are skipped
   with a warning rather than crashing the service.

Edits to `scheduler_jobs` take effect on the next backend restart.
"""
import logging

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from jobs.registry import JOBS
from repositories.scheduler import insert_default, list_jobs, record_run

logger = logging.getLogger(__name__)
TST = pytz.timezone("Asia/Taipei")


def _wrap(name: str, fn):
    """Wrap a job callable so each run stamps last_run_at / status."""
    def runner():
        try:
            fn()
        except Exception as e:
            logger.exception("scheduler_job_failed name=%s", name)
            record_run(name, "error", str(e)[:500])
        else:
            record_run(name, "ok", None)
    runner.__name__ = f"job_{name}"
    return runner


def _seed_defaults() -> None:
    for name, spec in JOBS.items():
        if insert_default(name, spec.default_cron):
            logger.info("scheduler_job_seeded name=%s cron=%s", name, spec.default_cron)


def start_scheduler() -> BackgroundScheduler:
    _seed_defaults()

    scheduler = BackgroundScheduler(timezone=TST)
    for row in list_jobs():
        name = row["name"]
        spec = JOBS.get(name)
        if spec is None:
            logger.warning("scheduler_job_unregistered name=%s", name)
            continue
        if not row["enabled"]:
            logger.info("scheduler_job_disabled name=%s", name)
            continue
        try:
            trigger = CronTrigger.from_crontab(row["cron_expr"], timezone=TST)
        except Exception as e:
            logger.error(
                "scheduler_cron_invalid name=%s expr=%r err=%s",
                name, row["cron_expr"], e,
            )
            continue
        scheduler.add_job(
            _wrap(name, spec.fn), trigger, id=name, replace_existing=True,
        )
        logger.info("scheduler_job_added name=%s cron=%s", name, row["cron_expr"])

    scheduler.start()
    return scheduler
