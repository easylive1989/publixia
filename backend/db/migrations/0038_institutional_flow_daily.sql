-- TWSE BFI82U 每日三大法人買賣金額原始資料。
--
-- 金額一律保存證交所回傳的整數「元」，不在 DB 存億元、淨額或成交比重：
--   - 各分項淨額 = buy - sell
--   - 法人成交比重 = (官方合計買進 + 官方合計賣出) / (市場成交金額 * 2)
-- 衍生值在 API 讀取時計算，避免重複來源漂移。

CREATE TABLE institutional_flow_daily (
    market                  TEXT NOT NULL,
    date                    TEXT NOT NULL,
    dealer_proprietary_buy  INTEGER NOT NULL,
    dealer_proprietary_sell INTEGER NOT NULL,
    dealer_hedge_buy        INTEGER NOT NULL,
    dealer_hedge_sell       INTEGER NOT NULL,
    trust_buy               INTEGER NOT NULL,
    trust_sell              INTEGER NOT NULL,
    foreign_buy             INTEGER NOT NULL,
    foreign_sell            INTEGER NOT NULL,
    foreign_dealer_buy      INTEGER NOT NULL,
    foreign_dealer_sell     INTEGER NOT NULL,
    total_buy               INTEGER NOT NULL,
    total_sell              INTEGER NOT NULL,
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (market, date)
);
