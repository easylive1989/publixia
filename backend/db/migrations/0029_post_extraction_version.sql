-- 0029_post_extraction_version.sql
-- 記錄每篇貼文「用哪個 prompt 版本解析的」，這樣 prompt 升版時能重抽「所有」舊貼文，
-- 包含被舊版錯誤解析成「無交易」的貼文（這些沒有 trade 列，舊的 stale 偵測抓不到）。
-- 既有 done 貼文此欄為 NULL，會被視為 stale → 下次 extract 用新版重抽。

ALTER TABLE posts ADD COLUMN extraction_version TEXT;
