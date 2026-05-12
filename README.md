# Publixia — Stock Dashboard

Personal stock + indicator dashboard.

- **Backend**: FastAPI on a VPS at `/opt/stock-dashboard/backend`, deployed via `.github/workflows/deploy-backend.yml`. Service: `stock-dashboard.service` (systemd).
- **Frontend**: Vite + React + Tailwind, deployed to GitHub Pages via `.github/workflows/deploy-frontend.yml`. Public URL: `https://stock.paul-learning.dev` (custom subdomain via DNS CNAME).

## 命名由來

**Publixia** /pʌbˈlɪk-si-ə/ 是一個結合「古羅馬歷史底蘊」與「現代軟體自動化」的自創詞，可從三個層次解讀：

1. **歷史溯源 — Publicani（羅馬稅收承包商）**
   人類最早的「法人組織」與「股份持有者」原型，西元前的羅馬廣場上即進行資本運作與權利轉讓。命名上借此表達回歸交易本質的精神。

2. **字根拆解**
   - `Publi-`：聯想 Public（公開市場）／ Publish（發布），意指「將個人交易策略發布到公開市場執行」。
   - `-ix`：常作為 Index（指標）或 Execute（執行）的縮寫，強調系統的精準。
   - `-ia`：常用於表示「領域」或「系統」（如 Utopia、Media），代表完整的策略生態系。

3. **功能轉譯 — The Public Market's Execution Axis（公開市場的執行軸心）**
   從混亂的公開資訊中，透過個人設定的邏輯，過濾出精確的執行信號。它不只是分析，更是個人策略在市場上的執行窗口。

定位一句話：**「傳承兩千年的交易智慧，結合現代 AI 的自動執行系統。」**

## Repository layout

```
backend/                 FastAPI app + scheduler + DB layer
frontend/                Vite/React app
admin/                   Standalone interactive admin CLI (users / tokens)
tests/                   pytest backend test suite (run from repo root)
stock-dashboard.service  systemd unit copied to VPS
deploy.sh                Manual VPS deploy (used outside CI)
.github/workflows/       CI: deploy-backend.yml, deploy-frontend.yml
```

## 資料與資料源

所有定時抓取的 fetcher 都註冊在 [`backend/jobs/registry.py`](backend/jobs/registry.py)，
排程實際時間從 `scheduler_jobs` 表讀取（cron 表達式為 Asia/Taipei）。
**所有快照都是日線**，schema 用 `UNIQUE(key, date)` 強制每日一筆 + upsert。

### 1. 大盤指數類 — `indicator_snapshots`

每個 indicator key 每天一筆，`value` 是當日數值、`extra_json` 放 metadata（漲跌幅、單位、燈號等）。

| indicator key                                                  | 內容                  | 資料來源                                                                                                | fetcher                          | 排程       |
|----------------------------------------------------------------|----------------------|---------------------------------------------------------------------------------------------------------|----------------------------------|------------|
| `taiex`                                                        | 加權指數              | yfinance `^TWII`                                                                                        | `fetchers/yfinance_fetcher.py`   | 14:00      |
| `fx`                                                           | 美金匯率              | yfinance `TWD=X`                                                                                        | `fetchers/yfinance_fetcher.py`   | 06:00      |
| `tw_futures`                                                   | 台指期 (TX) 近月收盤   | FinMind `TaiwanFuturesDaily`                                                                            | `fetchers/futures.py`            | 17:30      |
| `tw_volume`                                                    | 台股成交金額（億元）   | TWSE `openapi.twse.com.tw/v1/exchangeReport/FMTQIK`                                                     | `fetchers/volume.py`             | 18:05      |
| `us_volume`                                                    | S&P 500 成交量（億股）| yfinance `^GSPC`                                                                                        | `fetchers/volume.py`             | 06:10      |
| `fear_greed`                                                   | CNN Fear & Greed     | `production.dataviz.cnn.io/index/fearandgreed/graphdata`                                                | `fetchers/fear_greed.py`         | 08:00      |
| `ndc`                                                          | 景氣對策信號 (月度)   | NDC `index.ndc.gov.tw/n/json/data/eco/indicators`                                                       | `fetchers/ndc.py`                | 每月 1 號  |
| `margin_balance` / `short_balance` / `short_margin_ratio`      | 整體融資融券          | FinMind `TaiwanStockTotalMarginPurchaseShortSale`                                                       | `fetchers/chip_total.py`         | 18:00      |
| `total_foreign_net` / `total_trust_net` / `total_dealer_net`   | 整體三大法人買賣超     | FinMind `TaiwanStockTotalInstitutionalInvestors`                                                        | `fetchers/chip_total.py`         | 18:00      |

### 2. 個股與 watchlist — `watched_stocks` / `stock_snapshots`

- `watched_stocks` — 使用者自選清單，前端 `/api/stocks` 增刪。
- `stock_snapshots` — watchlist 每日收盤快照（yfinance；台股 14:00、美股 06:00）。
- 個股 K 線歷史 (`/api/stocks/{ticker}/history`) 是 **lazy fetch**，呼叫時即時跟 yfinance 拿 OHLCV，前端再計算 MA/MACD/KD。

### 3. 期貨 — FinMind `TaiwanFuturesDaily`

| 表                        | 內容                                                       | 排程             |
|---------------------------|-----------------------------------------------------------|------------------|
| `futures_daily`           | TX / MTX / TMF 每日 OHLCV + 未平倉 + 結算價（近月連續）        | 17:30            |
| `futures_settlement_dates`| TX 每月結算日；來源是人工維護的 [`backend/data/settlement_dates.md`](backend/data/settlement_dates.md)（TAIFEX 行事曆 PDF 摘錄）；fetcher 補未來 12 個月 | 每月 1 號 02:00 |

### 4. 三大法人 / 籌碼 — TAIFEX 每日下載 CSV

| 表                              | 來源                                                                     | 說明                                                                                                                  |
|---------------------------------|--------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| `institutional_futures_daily`   | TAIFEX `cht/3/futContractsDateDown`（三大法人 - 區分各期貨契約）            | 外資 TX/MTX 多空未平倉口數 + 金額（千元）                                                                              |
| `institutional_options_daily`   | TAIFEX `cht/3/callsAndPutsDateDown`（三大法人 - 選擇權買賣權分計）          | TXO 三大法人 × {CALL, PUT} 多空未平倉。自營商(避險)+(自行買賣) 合併為 `dealer`                                              |
| `tx_large_trader_daily`         | TAIFEX `cht/3/largeTraderFutDown`（大額交易人未沖銷部位結構表）              | TX combined contract（全月份合計、全交易人）top5/top10 多空口數，用來算散戶多空比                                          |
| `stock_chip_daily`              | FinMind（lazy fetch，呼叫個股頁時補資料）                                  | 個股三大法人買賣 + 融資融券餘額                                                                                          |

排程：`inst_futures` 18:00、`inst_options` 18:10、`large_trader` 18:05；外資期貨頁需 `can_view_foreign_futures` 權限。

### 5. 個股基本面 — FinMind（lazy fetch）

呼叫 `/api/stocks/{ticker}/{valuation,revenue,financial,dividend}` 時，
`fetchers/fundamentals_stock.py` 判斷快取是否新鮮、不足時跟 FinMind 補後寫入：

| 表                          | FinMind dataset                                                          | 回看範圍       |
|-----------------------------|--------------------------------------------------------------------------|----------------|
| `stock_per_daily`           | `TaiwanStockPER`（PER / PBR / 殖利率）                                    | 5 年           |
| `stock_revenue_monthly`     | `TaiwanStockMonthRevenue`                                                | 3 年           |
| `stock_financial_quarterly` | `TaiwanStockFinancialStatements` / `BalanceSheet` / `CashFlowsStatement` | 12 季 (3 年)   |
| `stock_dividend_history`    | `TaiwanStockDividend`                                                    | 10 年          |

每天 18:30 的 `watchlist_chip_per` 是 watchlist 主動暖快取的 cron，避免使用者第一次點進去要等。

### 6. 新聞 — RSS（記憶體快取）

`fetchers/news.py` 每 30 分鐘抓兩條鉅亨網 RSS（`tw_stock` + `headline`），結果只放 in-memory 快取，**不入 DB**。

### 7. 衍生資料 / 使用者狀態

| 表                      | 說明                                                                                                |
|-------------------------|----------------------------------------------------------------------------------------------------|
| `price_alerts`          | 使用者設的價格 / 指標警報，命中後透過 `core/discord.py` 發 Discord                                       |
| `strategies`            | 策略引擎 (TX/MTX/TMF) 的設定 + 假倉狀態機（idle/pending_entry/open/pending_exit），需 `can_use_strategy` 權限 |
| `strategy_signals`      | 每筆進場/出場 signal 與成交回報日誌                                                                  |
| `users` / `api_tokens`  | 使用者帳號 + bearer token（透過 admin CLI 管理）                                                       |
| `scheduler_jobs`        | 每個 job 的 cron 設定，admin CLI 可改，需重啟 backend 套用                                              |

### 8. 已停用

- **券商分點** (`stock_broker_daily`)：FinMind `TaiwanStockTradingDailyReport` 變成 Sponsor-only，表 / fetcher 保留但前端不再呼叫。

### 資料保留與備份

- `cleanup` job（週日 00:00）只留近 3 年。
- `backup_db` job（每日 03:00）把整顆 SQLite 上傳到 Cloudflare R2。
- 非交易日誤入的列由 `scripts/dedupe_non_trading_days.py` 一次性清理。

## GitHub Secrets required

Set these under **Settings → Secrets and variables → Actions**:

| Secret | Used by | What it is |
|---|---|---|
| `VPS_HOST` | `deploy-backend.yml` | VPS IP / hostname |
| `VPS_SSH_KEY` | `deploy-backend.yml` | Private key matching the VPS root key |
| `DISCORD_STOCK_WEBHOOK_URL` | `deploy-backend.yml` | Webhook for triggered alerts |
| `FINMIND_TOKEN` | `deploy-backend.yml` | FinMind API token (for chip / fundamentals) |

GitHub Pages must be set to **Settings → Pages → Source = GitHub Actions**.

## VPS environment variables

`stock-dashboard.service` reads `/opt/stock-dashboard/backend/.env`. To add or update a variable:

```bash
ssh root@$VPS_HOST
echo 'FOO=bar' >> /opt/stock-dashboard/backend/.env
systemctl restart stock-dashboard
```

`deploy-backend.yml` rewrites `.env` from GitHub Secrets on every deploy, so anything you add by hand will be overwritten on the next push. Add it as a Secret to make it durable.

## DB migrations

Schema changes go in `backend/db/migrations/NNNN_<snake_name>.sql` (4-digit forward-only). The runner (`backend/db/runner.py`) applies pending migrations on startup and records applied versions in `schema_migrations`.

Already-deployed migrations are immutable — make corrections by writing a new migration, never editing an old one.

## Auth bootstrap (first token)

The API enforces `Authorization: Bearer <token>` on every endpoint. Use
the standalone admin CLI in `admin/` to create users and issue tokens —
see [`admin/README.md`](admin/README.md) for setup.

```bash
# One-time venv setup
cd admin && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..

# Run interactively (defaults to backend/stock_dashboard.db)
admin/.venv/bin/python -m admin

# Or against an arbitrary DB file (e.g., a copy from the VPS)
DB_PATH=/tmp/sd.db admin/.venv/bin/python -m admin
```

The interactive flow covers: list users, create user, refresh token
(rotates the user's existing active token), and revoke. Issued tokens
are shown **once** — copy them immediately, then paste into the
dashboard's TokenGate prompt. The token is kept in browser `localStorage`;
the 🔓 重新登入 button on the header clears it.

## Disabled: 券商分點

`/api/stocks/{ticker}/brokers` returns an empty payload (`ok: false`). FinMind's `TaiwanStockTradingDailyReport` dataset went Sponsor-only; the fetcher / table / token are kept for future reactivation but the frontend no longer calls the endpoint.
