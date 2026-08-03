-- 0034_market_volume.sql
-- 大盤成交金額冷熱判讀的原始資料：每日 TWSE 集中市場成交統計（FMTQIK）。
--
-- 只存原始值（加權指數收盤、成交金額億元）；位階常態/量能比/殘差/百分位/判讀
-- 都在讀取時由 services/market_heat.py 以全歷史迴歸即時計算，不落地。
-- 由 market_volume_sync 排程每日增量同步（首跑自 2016-01 回補）。

CREATE TABLE market_volume_daily (
    date        TEXT PRIMARY KEY,          -- ISO YYYY-MM-DD（交易日）
    taiex_close REAL NOT NULL,             -- 發行量加權股價指數收盤
    turnover    REAL NOT NULL,             -- 成交金額（億元）
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
