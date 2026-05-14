-- 0019_drop_strategies.sql
--
-- Removes the futures-strategy + backtest feature in full:
--   * strategy_signals + strategies tables (migration 0008's payload)
--   * users.can_use_strategy permission flag
--   * users.discord_webhook_url (only ever consumed by strategy_notifier;
--     all other Discord pushes use the global DISCORD_STOCK_WEBHOOK_URL
--     setting)
--
-- strategy_signals is dropped first because of the FK cascade that 0008
-- declared from signals → strategies.
-- Requires SQLite ≥ 3.35 for ALTER TABLE DROP COLUMN.

DROP TABLE IF EXISTS strategy_signals;
DROP TABLE IF EXISTS strategies;
ALTER TABLE users DROP COLUMN can_use_strategy;
ALTER TABLE users DROP COLUMN discord_webhook_url;
