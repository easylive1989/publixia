-- 0036_market_scope.sql
-- 冷熱判讀從「只有台股大盤」擴成多市場（台股加權指數 + Nasdaq Composite）。
--
-- 兩件事：
--   1. 加 market 欄，主鍵 date → (market, date)。兩個市場的交易日曆不同，
--      本來就不該共用一個 date 主鍵。
--   2. taiex_close → index_close。這一欄現在也會放 Nasdaq Composite 收盤，
--      繼續叫 taiex_close 是直接騙人（DB 檔名/service 名沿用舊名是為了少churn，
--      但那是名字沒語意衝突；這一欄有）。
--
-- turnover 的單位隨市場而異，欄位本身只存數值：
--   TW → 成交金額（億元）      US → 成交股數（億股，Nasdaq composite volume）
-- 兩者都只在自己市場的歷史裡做迴歸與百分位，不跨市場比較，所以單位不同無妨。
--
-- SQLite 改不了主鍵，只能重建表再搬資料；既有列一律歸為 'TW'。

ALTER TABLE market_volume_daily RENAME TO market_volume_daily_old;

CREATE TABLE market_volume_daily (
    market      TEXT NOT NULL,             -- 'TW'（台股加權）/ 'US'（Nasdaq Composite）
    date        TEXT NOT NULL,             -- ISO YYYY-MM-DD（該市場的交易日）
    index_close REAL NOT NULL,             -- 指數收盤
    turnover    REAL NOT NULL,             -- 量能（單位依 market，見上）
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (market, date)
);

INSERT INTO market_volume_daily (market, date, index_close, turnover, updated_at)
SELECT 'TW', date, taiex_close, turnover, updated_at FROM market_volume_daily_old;

DROP TABLE market_volume_daily_old;
