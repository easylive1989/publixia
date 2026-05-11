-- 0016_txo_strike_oi_daily.sql
--
-- Daily market-wide TXO open interest broken down by 履約價 (strike).
-- Source: TAIFEX `選擇權每日交易行情` daily download (optDataDown). The
-- existing institutional_options_daily aggregates over all strikes per
-- identity × CALL/PUT; this table preserves per-strike granularity for
-- the 各履約價未平倉量分布 chart on the 外資期貨動向 page.
--
-- TAIFEX does not publish strike-level data per investor identity, so
-- this is market-wide totals only. Each calendar day yields thousands
-- of rows (strikes × contract months × CALL/PUT).
--
-- expiry_month is the original TAIFEX 到期月份(週別) string (e.g.
-- "202506", "202506W2") — kept as TEXT so weekly contracts are
-- distinguishable from monthly without extra normalisation.

CREATE TABLE txo_strike_oi_daily (
    symbol         TEXT    NOT NULL,    -- 'TXO'
    date           TEXT    NOT NULL,    -- YYYY-MM-DD
    expiry_month   TEXT    NOT NULL,    -- e.g. '202506', '202506W2'
    strike         REAL    NOT NULL,    -- 履約價
    put_call       TEXT    NOT NULL,    -- 'CALL' | 'PUT'
    open_interest  INTEGER NOT NULL,    -- 未沖銷契約量 (lots)
    settle_price   REAL,                -- 結算價 (optional, nullable)
    PRIMARY KEY (symbol, date, expiry_month, strike, put_call)
);

CREATE INDEX idx_txo_strike_oi_date          ON txo_strike_oi_daily(date);
CREATE INDEX idx_txo_strike_oi_date_expiry   ON txo_strike_oi_daily(date, expiry_month);
