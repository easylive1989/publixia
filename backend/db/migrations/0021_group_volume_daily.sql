-- 0021_group_volume_daily.sql
-- 族群（產業／主題）日成交量聚合表
--
-- Each row is one (trading_date, group_type, group_code) tuple representing
-- the day's total trading value/volume across stocks in that group.
--
-- group_type:
--   'industry' — TWSE industry classification from FinMind TaiwanStockInfo
--                (group_code/name = the Chinese category string, e.g. 半導體業)
--   'theme'    — future: hand-curated themes (AI, 軍工, ...) seeded from yaml

CREATE TABLE group_volume_daily (
    trade_date       TEXT    NOT NULL,
    group_type       TEXT    NOT NULL,
    group_code       TEXT    NOT NULL,
    group_name       TEXT    NOT NULL,
    total_value      REAL    NOT NULL,   -- 成交金額（新台幣元）
    total_volume     INTEGER NOT NULL,   -- 成交股數
    stock_count      INTEGER NOT NULL,
    mean_20d_value   REAL,                -- 過去 20 交易日 total_value 平均；不足 20 日為 NULL
    pct_vs_mean_20d  REAL,                -- (total_value - mean_20d_value) / mean_20d_value
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (trade_date, group_type, group_code)
);

CREATE INDEX idx_gvd_lookup ON group_volume_daily(group_type, trade_date DESC);
