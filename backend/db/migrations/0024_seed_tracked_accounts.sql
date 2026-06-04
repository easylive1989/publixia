-- 0024_seed_tracked_accounts.sql
-- 種子追蹤帳號。INSERT OR IGNORE → 對 (platform, handle) UNIQUE 冪等。
--
-- 爸逆逆 = Threads @ajhsu0820
-- 巴逆逆 = Threads @banini31
-- （巴逆逆的 FB 粉專與 Threads 內容重複，且無登入難爬，暫不納入）

INSERT OR IGNORE INTO tracked_accounts (person_key, display_name, platform, handle, profile_url)
VALUES ('dadnini', '爸逆逆', 'threads', 'ajhsu0820', 'https://www.threads.com/@ajhsu0820');

INSERT OR IGNORE INTO tracked_accounts (person_key, display_name, platform, handle, profile_url)
VALUES ('banini', '巴逆逆', 'threads', 'banini31', 'https://www.threads.com/@banini31');
