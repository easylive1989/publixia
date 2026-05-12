-- 0017_drop_top100.sql
--
-- Removes the Taiwan top-100 browse-list feature: drop the
-- auto_tracked_stocks table and the per-user can_view_top100 flag.
-- Requires SQLite ≥ 3.35 for ALTER TABLE DROP COLUMN.

DROP TABLE IF EXISTS auto_tracked_stocks;
ALTER TABLE users DROP COLUMN can_view_top100;
