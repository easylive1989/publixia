-- 0030_podcast_support.sql
-- Podcast 支援：podcast 貼文在 scrape 當下沒有逐字稿，content 先放空字串，
-- 由 transcription job 抓逐字稿填入後，才進入既有的 extraction queue。
--
-- transcript_status 是抽取閘門：
--   NULL  = 非音訊平台（threads）→ extract 立即可跑（行為不變）
--   pending|error → done = podcast，done 之後 extract 才看得到（見 posts.py 的 queue query）。

ALTER TABLE posts ADD COLUMN audio_url         TEXT;  -- enclosure 音檔 URL（podcast）
ALTER TABLE posts ADD COLUMN transcript_url    TEXT;  -- RSS <podcast:transcript> URL（若有）
ALTER TABLE posts ADD COLUMN transcript_status TEXT;  -- NULL=非音訊；pending|done|error（podcast）
ALTER TABLE posts ADD COLUMN transcript_source TEXT;  -- 'rss' | 'groq' | NULL（觀測用）
ALTER TABLE posts ADD COLUMN title             TEXT;  -- 集數標題（podcast item title；threads 為 NULL）

CREATE INDEX idx_posts_transcript_status ON posts(transcript_status);
