-- 0027_track_aoi.sql
-- 新增追蹤對象：Aoi（Threads @aoyamaa._）。INSERT OR IGNORE → 對 (platform, handle) 冪等。

INSERT OR IGNORE INTO tracked_accounts (person_key, display_name, platform, handle, profile_url)
VALUES ('aoi', 'Aoi', 'threads', 'aoyamaa._', 'https://www.threads.com/@aoyamaa._');
