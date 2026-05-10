-- 0011_foreign_futures_permission.sql
--
-- Adds a per-user feature flag that controls access to the Taiwan
-- foreign-investor futures-flow page (/futures/tw/foreign-flow).
-- Mirrors the can_use_strategy and can_view_top100 gating pattern —
-- admin grants the flag from the CLI; the /api/me response surfaces it;
-- the frontend hides the link and renders a permission gate when the
-- flag is off.

ALTER TABLE users ADD COLUMN can_view_foreign_futures INTEGER NOT NULL DEFAULT 0;
