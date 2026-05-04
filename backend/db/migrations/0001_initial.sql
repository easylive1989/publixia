-- 0001_initial.sql
-- Consolidated snapshot of the schema as of 2026-05-02.
-- For databases that already had this schema before the runner existed,
-- the runner's baseline mechanism marks this version as applied without
-- executing it (see db/runner.py).

CREATE TABLE indicator_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator  TEXT    NOT NULL,
    timestamp  TEXT    NOT NULL,
    value      REAL    NOT NULL,
    extra_json TEXT
);
CREATE INDEX idx_ind_ts ON indicator_snapshots(indicator, timestamp);

CREATE TABLE watched_stocks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker   TEXT NOT NULL UNIQUE,
    added_at TEXT NOT NULL
);

CREATE TABLE stock_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    price      REAL NOT NULL,
    change     REAL,
    change_pct REAL,
    currency   TEXT,
    name       TEXT
);
CREATE INDEX idx_stock_ts ON stock_snapshots(ticker, timestamp);

CREATE TABLE stock_broker_daily (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker               TEXT NOT NULL,
    date                 TEXT NOT NULL,
    securities_trader_id TEXT NOT NULL,
    securities_trader    TEXT,
    buy_volume           REAL NOT NULL DEFAULT 0,
    sell_volume          REAL NOT NULL DEFAULT 0,
    buy_amount           REAL NOT NULL DEFAULT 0,
    sell_amount          REAL NOT NULL DEFAULT 0,
    UNIQUE(ticker, date, securities_trader_id)
);
CREATE INDEX idx_broker_ticker_date ON stock_broker_daily(ticker, date);

CREATE TABLE stock_chip_daily (
    ticker         TEXT NOT NULL,
    date           TEXT NOT NULL,
    foreign_buy    REAL,
    foreign_sell   REAL,
    trust_buy      REAL,
    trust_sell     REAL,
    dealer_buy     REAL,
    dealer_sell    REAL,
    margin_balance REAL,
    short_balance  REAL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX idx_chip_ticker_date ON stock_chip_daily(ticker, date);

CREATE TABLE stock_per_daily (
    ticker         TEXT NOT NULL,
    date           TEXT NOT NULL,
    per            REAL,
    pbr            REAL,
    dividend_yield REAL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX idx_per_ticker_date ON stock_per_daily(ticker, date);

CREATE TABLE stock_revenue_monthly (
    ticker         TEXT    NOT NULL,
    year           INTEGER NOT NULL,
    month          INTEGER NOT NULL,
    revenue        REAL,
    announced_date TEXT,
    PRIMARY KEY (ticker, year, month)
);
CREATE INDEX idx_revenue_ticker_ym ON stock_revenue_monthly(ticker, year, month);

CREATE TABLE stock_financial_quarterly (
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,
    report_type TEXT NOT NULL,
    type        TEXT NOT NULL,
    value       REAL,
    PRIMARY KEY (ticker, date, report_type, type)
);
CREATE INDEX idx_financial_ticker_date ON stock_financial_quarterly(ticker, date, report_type);

CREATE TABLE stock_dividend_history (
    ticker            TEXT NOT NULL,
    year              TEXT NOT NULL,
    cash_dividend     REAL,
    stock_dividend    REAL,
    cash_ex_date      TEXT,
    cash_payment_date TEXT,
    announcement_date TEXT,
    PRIMARY KEY (ticker, year)
);
CREATE INDEX idx_dividend_ticker ON stock_dividend_history(ticker);

CREATE TABLE price_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type     TEXT NOT NULL,
    target          TEXT NOT NULL,
    condition       TEXT NOT NULL,
    threshold       REAL NOT NULL,
    enabled         INTEGER NOT NULL DEFAULT 1,
    triggered_at    TEXT,
    triggered_value REAL,
    created_at      TEXT NOT NULL,
    indicator_key   TEXT,
    window_n        INTEGER
);
CREATE INDEX idx_alert_target ON price_alerts(target_type, target, enabled);
