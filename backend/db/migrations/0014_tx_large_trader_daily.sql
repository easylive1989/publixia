-- 0014_tx_large_trader_daily.sql
--
-- Daily snapshot of TAIFEX「大額交易人未沖銷部位結構表」for 臺股期貨
-- (combined contract: TX + MTX/4 + TMF/20). Used to derive 散戶多空比
-- as ((market_oi - top10_long_oi) - (market_oi - top10_short_oi)) /
-- market_oi × 100 = (top10_short_oi - top10_long_oi) / market_oi × 100.
--
-- We pick:
--   商品(契約)   = "TX"
--   到期月份     = "999999" (全部月份合計)
--   交易人類別   = "0"      (全部交易人; "1" is 特定法人 only)
--
-- top5 columns are stored too — cheap, and lets future analysis pivot
-- without a re-fetch. Volumes are in 大台等量化口數 (TX-equivalent lots).

CREATE TABLE tx_large_trader_daily (
    date            TEXT    NOT NULL PRIMARY KEY,
    market_oi       INTEGER NOT NULL,
    top5_long_oi    INTEGER NOT NULL,
    top5_short_oi   INTEGER NOT NULL,
    top10_long_oi   INTEGER NOT NULL,
    top10_short_oi  INTEGER NOT NULL
);
