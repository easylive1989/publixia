-- 0020_purge_user_and_stock.sql
--
-- The dashboard is single-user, public-read from here on:
--   * no users / api_tokens / per-user permissions
--   * no per-user watchlist or alerts
--   * no individual-stock detail page → drop every stock_* snapshot table
--
-- Drop order matters because some of the legacy tables carry FK refs
-- (price_alerts → users, watched_stocks → users, api_tokens → users):
-- child tables first, parent (users) last.

-- per-user state
DROP TABLE IF EXISTS price_alerts;
DROP TABLE IF EXISTS watched_stocks;
DROP TABLE IF EXISTS api_tokens;

-- per-stock snapshot/fundamental tables (individual stock detail page is gone)
DROP TABLE IF EXISTS stock_broker_daily;
DROP TABLE IF EXISTS stock_chip_daily;
DROP TABLE IF EXISTS stock_dividend_history;
DROP TABLE IF EXISTS stock_financial_quarterly;
DROP TABLE IF EXISTS stock_per_daily;
DROP TABLE IF EXISTS stock_revenue_monthly;
DROP TABLE IF EXISTS stock_snapshots;

-- finally the user concept itself
DROP TABLE IF EXISTS users;
