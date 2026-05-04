-- 0005_snapshot_date_dedupe.sql
-- 把 indicator_snapshots / stock_snapshots 從盤中多筆轉成每日一筆。
-- 1) 新增 date 欄位,從 timestamp 反推 (前 10 字元 = YYYY-MM-DD)
-- 2) 同一 (key, date) 只保留 id 最大 (= timestamp 最新) 那筆,刪除其餘
-- 3) 建 UNIQUE INDEX 以支援後續 ON CONFLICT(key, date) 的 upsert

ALTER TABLE indicator_snapshots ADD COLUMN date TEXT;
UPDATE indicator_snapshots SET date = substr(timestamp, 1, 10) WHERE date IS NULL;
DELETE FROM indicator_snapshots
 WHERE id NOT IN (
     SELECT MAX(id) FROM indicator_snapshots GROUP BY indicator, date
 );
CREATE UNIQUE INDEX idx_ind_date ON indicator_snapshots(indicator, date);

ALTER TABLE stock_snapshots ADD COLUMN date TEXT;
UPDATE stock_snapshots SET date = substr(timestamp, 1, 10) WHERE date IS NULL;
DELETE FROM stock_snapshots
 WHERE id NOT IN (
     SELECT MAX(id) FROM stock_snapshots GROUP BY ticker, date
 );
CREATE UNIQUE INDEX idx_stock_date ON stock_snapshots(ticker, date);
