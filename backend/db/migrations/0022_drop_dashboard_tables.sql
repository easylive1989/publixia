-- 0022_drop_dashboard_tables.sql
-- 全面改版：移除舊「股市指標儀表板」的所有領域資料表。
--
-- 產品從總體股市指標儀表板轉向「跟單追蹤器」（追蹤 Threads 貼文、AI 解析買賣）。
-- 舊功能完全移除。保留 schema_migrations（runner 記錄）與 scheduler_jobs（沿用）。
--
-- 破壞性且不可逆——forward-only runner 在每次啟動套用。drop 清單為「現行 schema
-- 產生的表」與「更早期 legacy 表」的聯集，全部 IF EXISTS，對任何版本的 DB 皆冪等。

-- 現行 schema（migration 產生）
DROP TABLE IF EXISTS indicator_snapshots;
DROP TABLE IF EXISTS futures_daily;
DROP TABLE IF EXISTS futures_settlement_dates;
DROP TABLE IF EXISTS institutional_futures_daily;
DROP TABLE IF EXISTS institutional_options_daily;
DROP TABLE IF EXISTS txo_strike_oi_daily;
DROP TABLE IF EXISTS tx_large_trader_daily;
DROP TABLE IF EXISTS group_volume_daily;
DROP TABLE IF EXISTS foreign_flow_ai_reports;

-- 早期 legacy 表（部分舊 DB 仍殘留）
DROP TABLE IF EXISTS api_tokens;
DROP TABLE IF EXISTS auto_tracked_stocks;
DROP TABLE IF EXISTS watched_stocks;
DROP TABLE IF EXISTS price_alerts;
DROP TABLE IF EXISTS strategies;
DROP TABLE IF EXISTS strategy_signals;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS stock_snapshots;
DROP TABLE IF EXISTS stock_broker_daily;
DROP TABLE IF EXISTS stock_chip_daily;
DROP TABLE IF EXISTS stock_per_daily;
DROP TABLE IF EXISTS stock_revenue_monthly;
DROP TABLE IF EXISTS stock_financial_quarterly;
DROP TABLE IF EXISTS stock_dividend_history;
