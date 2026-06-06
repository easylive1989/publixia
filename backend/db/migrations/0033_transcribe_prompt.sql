-- 0033_transcribe_prompt.sql
-- 節目專屬的 Whisper 轉錄 prompt：餵正確的節目名/主持人/常見詞當聲學脈絡，
-- 改善專有名詞誤判（例：股癌被聽成「谷外」、謝孟恭被聽成「星夢宮」）。
ALTER TABLE tracked_accounts ADD COLUMN transcribe_prompt TEXT;

UPDATE tracked_accounts
   SET transcribe_prompt = '歡迎收聽股癌，我是謝孟恭。以下是台灣股市投資的繁體中文內容，常提到台積電、輝達、聯發科、台股、美股、財報、半導體。'
 WHERE platform='podcast' AND handle='gooaye';

-- 重轉已存的股癌集數（先前以無 prompt 轉出，專有名詞誤判）：
-- 清空 content、transcript_status 回 pending → transcribe job 用新 prompt 重轉，
-- 重轉完內容回填、自動重抽訊號。
UPDATE posts
   SET content='', transcript_status='pending'
 WHERE platform='podcast'
   AND account_id IN (SELECT id FROM tracked_accounts WHERE handle='gooaye' AND platform='podcast');
