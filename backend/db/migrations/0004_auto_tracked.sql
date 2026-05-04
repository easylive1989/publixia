-- 0004_auto_tracked.sql

CREATE TABLE auto_tracked_stocks (
    ticker     TEXT PRIMARY KEY,
    source     TEXT NOT NULL DEFAULT 'twse-top100',
    added_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
