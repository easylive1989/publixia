-- 0006_futures_daily.sql
-- 台灣指數期貨 (TX) 日線 OHLCV 快取表。
-- 來源:FinMind TaiwanFuturesDaily,每日選擇近月合約一筆。
-- 用途:Dashboard 卡片即時值來自 indicator_snapshots(tw_futures);
--      詳細頁的 K 線圖、成交量、技術指標則查這張表(歷史可長達數年)。

CREATE TABLE futures_daily (
    symbol         TEXT NOT NULL,
    date           TEXT NOT NULL,
    contract_date  TEXT,
    open           REAL,
    high           REAL,
    low            REAL,
    close          REAL,
    volume         REAL,
    open_interest  REAL,
    settlement     REAL,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX idx_futures_symbol_date ON futures_daily(symbol, date);
