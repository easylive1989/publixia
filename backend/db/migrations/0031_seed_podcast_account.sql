-- 0031_seed_podcast_account.sql
-- 種子 podcast 追蹤帳號（範本）。
--
-- Podcast 帳號是「資料驅動」的：新增一個節目 = 插入一筆 platform='podcast' 的 row，
-- 其中 profile_url 放「RSS feed URL」（PodcastScraper 讀的就是這個欄位），
-- handle 放節目的穩定 slug（滿足 UNIQUE(platform, handle)）。
--
-- Gooaye 股癌（SoundOn）。先以 enabled=0 種子，避免排程器一上線就 backfill
-- 三個月 backlog、一次吃掉 Groq 每日額度。確認單集流程沒問題後，再用後續
-- migration 把 enabled 打開（並視需要調整 backfill_months）。
-- backfill_months=1：日後啟用時也只回補近一個月，控制轉錄量。
INSERT OR IGNORE INTO tracked_accounts
    (person_key, display_name, platform, handle, profile_url, enabled, backfill_months)
VALUES
    ('gooaye', '股癌', 'podcast', 'gooaye',
     'https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml',
     0, 1);
