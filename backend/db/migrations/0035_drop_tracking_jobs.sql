-- 追蹤（Threads/podcast 喊單）那條線整條移除後，scheduler_jobs 裡的舊列已經
-- 沒有對應的 registry entry，每次啟動只會刷 scheduler_job_unregistered 警告。
-- 清掉排程列即可；posts / extracted_trades / tracked_accounts 等資料表刻意保留
-- （唯一的還原點是 R2 夜間備份，不做無法回頭的 DROP）。
DELETE FROM scheduler_jobs
WHERE name IN (
    'scrape_accounts',
    'transcribe_podcasts',
    'extract_trades',
    'price_tracking',
    'stock_ref_sync'
);
