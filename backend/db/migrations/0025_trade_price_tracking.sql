-- 0025_trade_price_tracking.sql
-- 貼文提到的個股，從貼文當下買入後的 7 日 / 1 月漲跌幅追蹤。
--
-- 一列 = 一篇貼文提到的一檔股票（去重 direction）。進場價 = 貼文當日（或之後
-- 第一個交易日）收盤；7d/1m = 各窗口內最後交易日收盤算 %；窗口未過完則為 NULL。
-- 由 price_tracking 排程每日計算/更新，status 從 pending → partial → done。

CREATE TABLE trade_price_tracking (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    ticker      TEXT    NOT NULL,
    market      TEXT    NOT NULL,            -- 'TW' | 'US'
    base_date   TEXT,                         -- 實際採用的進場交易日
    base_price  REAL,
    price_7d    REAL,
    price_1m    REAL,
    pct_7d      REAL,                          -- (price_7d - base_price) / base_price
    pct_1m      REAL,
    status      TEXT    NOT NULL DEFAULT 'pending',  -- pending|partial|done|unavailable
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (post_id, ticker)
);

CREATE INDEX idx_tpt_post ON trade_price_tracking(post_id);
CREATE INDEX idx_tpt_status ON trade_price_tracking(status);
