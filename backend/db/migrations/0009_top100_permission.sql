-- 0009_top100_permission.sql
--
-- Adds a per-user feature flag that controls access to the Taiwan top-100
-- (auto_tracked_stocks) browse list. Mirrors the can_use_strategy gating
-- pattern from migration 0008 — admin grants the flag from the CLI; the
-- /api/me response surfaces it; the frontend hides the link and renders a
-- permission gate when the flag is off.

ALTER TABLE users ADD COLUMN can_view_top100 INTEGER NOT NULL DEFAULT 0;
