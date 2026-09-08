-- 成功送達 Discord 後才記錄金額指紋，避免早晚同步、重跑或重啟後重複通知。
CREATE TABLE institutional_flow_notifications (
    market TEXT NOT NULL,
    date TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (market, date)
);
