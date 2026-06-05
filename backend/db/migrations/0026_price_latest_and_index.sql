-- 0026_price_latest_and_index.sql
-- (1) trade_price_tracking 增加「最新價（當前價）」欄位，前端多顯示一行「最新」成效。
-- (2) 把「大盤／台股／加權」對應到加權指數（TAIEX = Yahoo ^TWII），用指數點數算成效。

ALTER TABLE trade_price_tracking ADD COLUMN price_latest REAL;
ALTER TABLE trade_price_tracking ADD COLUMN pct_latest REAL;
ALTER TABLE trade_price_tracking ADD COLUMN latest_date TEXT;

-- 加權指數作為一個可追蹤標的（market='INDEX'）。aliases 讓 normalization 把
-- 台股/大盤/加權… 對應到它。price_history 會把 ticker 'TAIEX' 轉成 Yahoo '^TWII'。
INSERT OR IGNORE INTO stock_reference (ticker, market, canonical_name, aliases, source)
VALUES (
  'TAIEX', 'INDEX', '加權指數',
  '["台股","大盤","加權","加權指數","台股大盤","大盤指數","台股指數","指數","集中市場"]',
  'static'
);
