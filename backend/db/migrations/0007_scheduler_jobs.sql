-- 0007_scheduler_jobs.sql
-- Per-job schedule configuration. Backend boots, ensures every job in the
-- code-side registry has a row (insert-if-missing — never overwrites user
-- edits), then reads cron_expr / enabled to wire up APScheduler.
--
-- Admin CLI edits these rows to retime / pause jobs; changes take effect
-- on backend restart.

CREATE TABLE scheduler_jobs (
    name         TEXT PRIMARY KEY,
    cron_expr    TEXT NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 1,
    last_run_at  TEXT,
    last_status  TEXT,
    last_error   TEXT,
    updated_at   TEXT NOT NULL
);
