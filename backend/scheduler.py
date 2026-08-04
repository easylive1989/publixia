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

from core.alerts import send_alert
from jobs.registry import JOBS, JobSpec
from repositories.scheduler import insert_default, list_jobs, record_run

logger = logging.getLogger(__name__)
TST = pytz.timezone("Asia/Taipei")


def _wrap(name: str, spec: JobSpec, cron: str):
    """Wrap a job callable so each run stamps last_run_at / status.

    失敗一律推 Discord。排程沒人盯，log 要有人主動去翻才看得到，而一支每天
    只跑一次的 job 壞掉可以壞很久都沒人發現 —— 通報要自己找上門。
    """
    def runner():
        try:
            result = spec.fn()
        except Exception as e:
            logger.exception("scheduler_job_failed name=%s", name)
            record_run(name, "error", f"{type(e).__name__}: {e}"[:500])
            send_alert(
                f"排程失敗｜{name}",
                error=e,
                fields={
                    "工作": spec.description,
                    "排程": f"`{cron}`（Asia/Taipei）",
                    "查 log": f"`journalctl -u stock-dashboard --since today | grep {name}`",
                },
            )
        else:
            record_run(name, "ok", None)
            logger.info("scheduler_job_ok name=%s result=%s", name, result)
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
            # 掛不上的 job 不會有任何執行紀錄，光看 scheduler_jobs 也看不出
            # 異常（last_run_at 就只是一直沒更新）—— 開機當下就得講。
            logger.error(
                "scheduler_cron_invalid name=%s expr=%r err=%s",
                name, row["cron_expr"], e,
            )
            send_alert(
                f"排程掛不上｜{name}",
                error=e,
                fields={
                    "cron_expr": f"`{row['cron_expr']}`",
                    "後果": "這支 job 完全不會執行，直到 scheduler_jobs 的 "
                            "cron_expr 修好並重啟 backend",
                },
            )
            continue
        scheduler.add_job(
            _wrap(name, spec, row["cron_expr"]), trigger, id=name,
            replace_existing=True,
        )
        logger.info("scheduler_job_added name=%s cron=%s", name, row["cron_expr"])

    scheduler.start()
    return scheduler
