-- 0032_enable_gooaye.sql
-- 啟用股癌 podcast 追蹤。0031 先以 enabled=0 種子（避免一上線就 backfill），
-- 單集流程確認後在此打開：排程器下一個 scrape tick 會回補近一個月集數
-- （backfill_months=1），transcribe job 以「最新優先」逐集轉錄。
UPDATE tracked_accounts SET enabled=1, updated_at=datetime('now')
WHERE platform='podcast' AND handle='gooaye';
