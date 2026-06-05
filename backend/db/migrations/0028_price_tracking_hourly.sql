-- 0028_price_tracking_hourly.sql
-- 撤掉獨立的 price_tracking 排程：解析貼文後會直接接一輪價格更新，
-- 不需要另一個 cron 重複跑。

DELETE FROM scheduler_jobs WHERE name = 'price_tracking';
