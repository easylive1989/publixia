-- 0015_institutional_options_daily.sql
--
-- Daily snapshot of three-major-investor (外資 / 投信 / 自營商) options
-- positions. Source: TAIFEX `三大法人 - 選擇權買賣權分計` daily CSV
-- (callsAndPutsDateDown). Currently only TXO (台指選擇權) is ingested.
--
-- Each calendar day yields 6 rows per product: 3 identities × {CALL, PUT}.
-- Volumes are in 口 (lots, integer); amounts are in 千元 (TAIFEX native),
-- to mirror institutional_futures_daily so amount-formatting logic can
-- be shared.
--
-- 自營商 sub-categories ("自營商(避險)", "自營商(自行買賣)") are summed
-- into a single 'dealer' identity before insertion — see
-- fetchers.institutional_options.

CREATE TABLE institutional_options_daily (
    symbol       TEXT    NOT NULL,
    date         TEXT    NOT NULL,
    identity     TEXT    NOT NULL,   -- 'foreign' | 'investment_trust' | 'dealer'
    put_call     TEXT    NOT NULL,   -- 'CALL' | 'PUT'
    long_oi      INTEGER NOT NULL,
    short_oi     INTEGER NOT NULL,
    long_amount  REAL    NOT NULL,
    short_amount REAL    NOT NULL,
    PRIMARY KEY (symbol, date, identity, put_call)
);

CREATE INDEX idx_inst_opt_date ON institutional_options_daily(date);
