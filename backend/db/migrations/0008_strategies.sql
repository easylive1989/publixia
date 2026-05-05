-- 0008_strategies.sql
--
-- Futures Strategy Engine — full schema in one shot.
-- See docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md
-- §3 for the design.
--
-- Adds two columns to users (permission flag + per-user Discord webhook),
-- and two new tables: strategies (with embedded hypothetical-position
-- state) and strategy_signals (entry/exit signal + fill log).

ALTER TABLE users ADD COLUMN can_use_strategy INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN discord_webhook_url TEXT;

CREATE TABLE strategies (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                     TEXT    NOT NULL,
    direction                TEXT    NOT NULL CHECK (direction IN ('long','short')),
    contract                 TEXT    NOT NULL CHECK (contract  IN ('TX','MTX','TMF')),
    contract_size            INTEGER NOT NULL DEFAULT 1,
    max_hold_days            INTEGER,
    entry_dsl                TEXT    NOT NULL,
    take_profit_dsl          TEXT    NOT NULL,
    stop_loss_dsl            TEXT    NOT NULL,
    notify_enabled           INTEGER NOT NULL DEFAULT 0,

    state                    TEXT    NOT NULL DEFAULT 'idle'
                              CHECK (state IN ('idle','pending_entry','open','pending_exit')),
    entry_signal_date        TEXT,
    entry_fill_date          TEXT,
    entry_fill_price         REAL,
    pending_exit_kind        TEXT,
    pending_exit_signal_date TEXT,

    last_error               TEXT,
    last_error_at            TEXT,

    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL,
    UNIQUE(user_id, name)
);

CREATE INDEX idx_strategies_user        ON strategies(user_id);
CREATE INDEX idx_strategies_notify_open ON strategies(notify_enabled, state)
                                            WHERE notify_enabled = 1;

CREATE TABLE strategy_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id     INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    kind            TEXT    NOT NULL CHECK (kind IN (
                      'ENTRY_SIGNAL', 'ENTRY_FILLED',
                      'EXIT_SIGNAL',  'EXIT_FILLED',
                      'MANUAL_RESET', 'RUNTIME_ERROR'
                    )),
    signal_date     TEXT    NOT NULL,
    close_at_signal REAL,
    fill_price      REAL,
    exit_reason     TEXT,
    pnl_points      REAL,
    pnl_amount      REAL,
    message         TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX idx_signals_strategy_date ON strategy_signals(strategy_id, signal_date DESC);
