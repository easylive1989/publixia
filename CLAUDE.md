# CLAUDE.md

## 現行產品

Publixia 是單市場的**台股大盤成交金額冷熱判讀**。它同步加權指數收盤與 TWSE
成交金額，以 `ln(量能) ~ ln(指數)` OLS 位階常態、殘差近一年百分位產生五級判讀。

Repo 過去做過期貨策略引擎、跟單追蹤與 Nasdaq 判讀；那些 migration 和設計文件是
歷史，不是現行功能。不要把舊功能重新接回來。US 歷史 DB 列刻意保留，但 API、前端
與排程只接受 TW。

## 開發與測試

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000

python3 -m pytest tests/
cd frontend && npm test
```

後端測試從 repo root 執行；`tests/conftest.py` 使用記憶體 DB。前端是 Vite + React，
開發 API proxy 指向 `127.0.0.1:8000`。

## 後端架構

- `backend/main.py`：FastAPI app。
- `backend/api/routes/market.py`：`volume-heat`、`regimes` 與 refresh API。
- `backend/core/twse.py`：FMTQIK 收盤月報。
- `backend/core/twse_intraday.py`：MIS 盤中快照。
- `backend/repositories/market_volume.py`：原始日資料存取。
- `backend/services/market_heat.py`：OLS、殘差、百分位、五級判讀。
- `backend/services/intraday_heat.py`：13:00 線性外推與 Discord 推播。
- `backend/jobs/registry.py` + `scheduler.py`：DB-driven APScheduler。
- `backend/db/runner.py`：forward-only migration runner。

資料庫只存 `(market, date, index_close, turnover)` 原始值，所有衍生值讀取時計算。
現行程式只寫/read TW；不要刪除既有 US 列，除非使用者另行確認。

## API 契約

- `GET /api/market/volume-heat?market=TW&days=N`：畫面完整資料。
- `GET /api/market/regimes?market=TW`：給研究工具的 `schema_version=1` 小型契約。
- `POST /api/market/volume-heat/refresh?market=TW`：背景同步。

`regimes.level` 的機器值為 `very_cold/cold/normal/hot/very_hot`。消費端不可解析中文
label。修改契約時必須升 `schema_version`，避免讓保存快照的回測靜默誤讀。

## 排程

- `intraday_heat_signal`：`0 13 * * 1-5`
- `market_volume_sync`：`0 16 * * 1-5`
- `backup_db`：`0 3 * * *`

Cron 是 POSIX 星期語義（0=週日），必須經 `jobs/cron.py::crontab_trigger` 轉譯，不能
直接交給 `CronTrigger.from_crontab`，否則週一到週五會平移成週二到週六。

Migration `0037_remove_nasdaq_sync.sql` 會清除已部署 DB 裡殘留的 Nasdaq job row；
registry 也已移除該 callable。

## 失敗必須有聲音

排程例外由 `scheduler._wrap` 記錄並透過 `send_alert` 推 Discord。服務層拿不到有效
結果時應拋出帶定位資訊的例外，不能安靜 return。休市使用 `MarketClosed`，讓 Discord
明確說明未判讀原因。`send_alert` 自己不得再往外拋例外。

MIS 的 `getStatis.jsp` 必須帶 `_=<epoch 毫秒>`，值在 `detail.tz`（元）；`tv` 是張數，
不能混用。盤中估算不得寫入 `market_volume_daily`，避免把估計值顯示成正式收盤資料。

## 前端

單頁只呈現台股：區間 tabs、半年 dropdown、今日判讀、量能圖、指數圖與明細表。
`frontend/src/lib/markets.ts` 仍保留 `MarketConfig`，集中管理台股欄位名稱與單位；不要
重新加入市場切換 UI。`MethodPage` 必須與 `market_heat.py` 的算法同步。

## 部署與安全

- Push `master` 後依 backend/frontend path filter 部署。
- Backend 固定 `/opt/stock-dashboard/backend`，service 名沿用 `stock-dashboard.service`。
- Frontend 從 `stock.paul-learning.dev/` 根路徑提供。
- 啟動時自動套 migration；已部署 migration 不可修改，只能新增下一支。
- `.env`、webhook、VPS hostname、SSH key、API token 不得提交。
- 每次 deploy 會從 GitHub Secrets 重寫 VPS `.env`，手動修改不會持久。
