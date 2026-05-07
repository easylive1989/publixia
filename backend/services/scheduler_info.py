"""Compute next-run-at for scheduled jobs.

Reads `scheduler_jobs.cron_expr` for the requested job and returns the
next fire time according to APScheduler's CronTrigger, in TST. Disabled
or unknown jobs return None.
"""
from datetime import datetime

import pytz
from apscheduler.triggers.cron import CronTrigger

from repositories.scheduler import get_job

TST = pytz.timezone("Asia/Taipei")


def next_run_at(job_name: str) -> datetime | None:
    row = get_job(job_name)
    if row is None or not row["enabled"]:
        return None
    try:
        trigger = CronTrigger.from_crontab(row["cron_expr"], timezone=TST)
    except Exception:
        return None
    return trigger.get_next_fire_time(None, datetime.now(TST))
