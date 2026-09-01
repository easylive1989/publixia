-- Publixia 收斂回台股單市場。Nasdaq 的歷史 market_volume_daily 資料刻意保留，
-- 只移除會繼續抓取資料的排程設定，避免不可逆地刪除既有研究資料。
DELETE FROM scheduler_jobs WHERE name = 'nasdaq_volume_sync';
