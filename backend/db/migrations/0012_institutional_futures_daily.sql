-- 0012_institutional_futures_daily.sql
--
-- Daily snapshot of foreign-investor futures positions (TX 大台 + MTX
-- 小台). Source: Taiwan Futures Exchange "三大法人 - 區分各期貨契約"
-- daily CSV.
--
-- Volumes are kept in 口 (lots, integer). Amounts are in 千元 (thousand
-- TWD) which is the unit the exchange CSV uses; downstream metric
-- computation reuses this unit and only converts at presentation time.
--
-- Keyed on (symbol, date) so the upsert pattern from
-- repositories.futures.save_futures_daily_rows transfers cleanly.

CREATE TABLE institutional_futures_daily (
    symbol               TEXT    NOT NULL,
    date                 TEXT    NOT NULL,
    foreign_long_oi      INTEGER NOT NULL,
    foreign_short_oi     INTEGER NOT NULL,
    foreign_long_amount  REAL    NOT NULL,
    foreign_short_amount REAL    NOT NULL,
    PRIMARY KEY (symbol, date)
);

CREATE INDEX idx_inst_fut_date ON institutional_futures_daily(date);
