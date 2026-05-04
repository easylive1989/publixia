-- 0003_users.sql

CREATE TABLE users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO users (name) VALUES ('paul');

ALTER TABLE api_tokens ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1
    REFERENCES users(id);
CREATE UNIQUE INDEX idx_api_tokens_active_user
    ON api_tokens(user_id) WHERE revoked_at IS NULL;

ALTER TABLE price_alerts ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1
    REFERENCES users(id);
CREATE INDEX idx_alert_user ON price_alerts(user_id, enabled);

CREATE TABLE watched_stocks_new (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker   TEXT NOT NULL,
    user_id  INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
    added_at TEXT NOT NULL,
    UNIQUE(user_id, ticker)
);
INSERT INTO watched_stocks_new (id, ticker, user_id, added_at)
SELECT id, ticker, 1, added_at FROM watched_stocks;
DROP TABLE watched_stocks;
ALTER TABLE watched_stocks_new RENAME TO watched_stocks;
CREATE INDEX idx_watched_user ON watched_stocks(user_id);
