-- 0028_price_tracking_hourly.sql
-- 把 price_tracking 從每 6 小時拉密到每小時。只在 row 還是舊預設值時覆寫，
-- 不動到管理員可能改過的自訂排程。

UPDATE scheduler_jobs
SET cron_expr = '0 * * * *', updated_at = datetime('now')
WHERE name = 'price_tracking' AND cron_expr = '0 */6 * * *';
