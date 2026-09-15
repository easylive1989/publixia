-- 0040_market_breadth_daily.sql
-- 台股每日市場寬度，來源為 TWSE MI_INDEX 的「漲跌證券數合計／股票」欄。
--
-- 只保存官方原始家數；恐懼貪婪代理指數及其五個子分數在讀取時由
-- services/market_sentiment.py 計算，避免把衍生值永久凍結在資料庫。

CREATE TABLE market_breadth_daily (
    market      TEXT NOT NULL,
    date        TEXT NOT NULL,
    advancing   INTEGER NOT NULL CHECK (advancing >= 0),
    declining   INTEGER NOT NULL CHECK (declining >= 0),
    unchanged   INTEGER NOT NULL CHECK (unchanged >= 0),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (market, date)
);
