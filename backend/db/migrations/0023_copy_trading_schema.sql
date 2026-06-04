-- 0023_copy_trading_schema.sql
-- 跟單追蹤器核心 schema。
--
-- tracked_accounts  追蹤的人 + 其社群帳號（data-driven，可多平台多帳號）
-- posts             每篇爬到的貼文（platform_post_id 去重）
-- extracted_trades  每篇貼文 AI 解析出的 0..N 筆買賣訊號
-- stock_reference   股票名稱/代號正規化對照（台股來自 FinMind，美股靜態維護）
--
-- 慣例對齊 0021：PK / UNIQUE 當 upsert key，時間欄位 TEXT DEFAULT (datetime('now'))。

CREATE TABLE tracked_accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    person_key      TEXT    NOT NULL,            -- 穩定 slug，同一人多平台共用，例：'banini'
    display_name    TEXT    NOT NULL,            -- 巴逆逆
    platform        TEXT    NOT NULL,            -- 'threads'（未來可加 'facebook'）
    handle          TEXT    NOT NULL,            -- 'banini31'
    profile_url     TEXT    NOT NULL,
    enabled         INTEGER NOT NULL DEFAULT 1,
    session_cookie  TEXT,                         -- 選用：登入 cookie（無登入優先，擋住才用）
    backfill_months INTEGER NOT NULL DEFAULT 3,
    avatar_url      TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (platform, handle)
);

CREATE INDEX idx_tracked_person ON tracked_accounts(person_key);

CREATE TABLE posts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id        INTEGER NOT NULL REFERENCES tracked_accounts(id),
    platform          TEXT    NOT NULL,
    platform_post_id  TEXT    NOT NULL,          -- 平台原生 id（Threads shortcode）
    url               TEXT    NOT NULL,
    content           TEXT    NOT NULL,          -- 貼文原文
    posted_at         TEXT,                       -- ISO ；未知為 NULL
    scraped_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    extraction_status TEXT    NOT NULL DEFAULT 'pending',  -- pending|done|error|skipped
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (platform, platform_post_id)
);

CREATE INDEX idx_posts_account_time ON posts(account_id, posted_at DESC);
CREATE INDEX idx_posts_status ON posts(extraction_status);

CREATE TABLE extracted_trades (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id        INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    raw_symbol     TEXT    NOT NULL,             -- 貼文裡實際用的字串（台積電 / 小台電 / 2330）
    ticker         TEXT,                          -- 正規化代號；對不到為 NULL
    market         TEXT,                          -- 'TW' | 'US' | NULL
    direction      TEXT    NOT NULL,             -- buy|sell|hold|bullish|bearish
    price          REAL,
    quantity       REAL,
    trade_date     TEXT,
    confidence     REAL    NOT NULL,             -- 0..1 AI 信心
    model          TEXT    NOT NULL,
    prompt_version TEXT    NOT NULL,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (post_id, raw_symbol, direction)
);

CREATE INDEX idx_trades_post ON extracted_trades(post_id);

CREATE TABLE stock_reference (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT    NOT NULL,             -- 2330 / TSM
    market         TEXT    NOT NULL,             -- 'TW' | 'US'
    canonical_name TEXT    NOT NULL,             -- 台積電 / Taiwan Semiconductor
    aliases        TEXT,                          -- JSON array，別名/暱稱
    source         TEXT    NOT NULL,             -- 'finmind' | 'static'
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (market, ticker)
);

CREATE INDEX idx_stockref_name ON stock_reference(canonical_name);
