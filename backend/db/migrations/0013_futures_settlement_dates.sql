-- 0013_futures_settlement_dates.sql
--
-- Final-settlement dates per futures contract month. Currently only TX
-- is populated; the schema leaves room to track MTX/TMF separately if
-- ever needed (their settlement calendar mirrors TX in practice).
--
-- Refreshed by fetchers.futures_settlement on a monthly cadence (writes
-- the next ~12 months) plus a one-shot historical backfill.

CREATE TABLE futures_settlement_dates (
    symbol          TEXT NOT NULL,           -- 'TX'
    year_month      TEXT NOT NULL,           -- 'YYYY-MM'
    settlement_date TEXT NOT NULL,           -- 'YYYY-MM-DD'
    PRIMARY KEY (symbol, year_month)
);

CREATE INDEX idx_fut_settlement_date ON futures_settlement_dates(settlement_date);
