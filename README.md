# Publixia — 跟單追蹤器 (Copy-Trading Tracker)

追蹤特定人物的社群貼文，用 AI 解析出他們買賣了哪些股票，並追蹤每筆標的從貼文當下算起的漲跌幅。

- **Backend**: FastAPI on a VPS at `/opt/stock-dashboard/backend`, deployed via `.github/workflows/deploy-backend.yml`. Service: `stock-dashboard.service` (systemd). API: `https://api.paul-learning.dev`.
- **Frontend**: Vite + React + Tailwind, deployed to GitHub Pages via `.github/workflows/deploy-frontend.yml`. Public URL: `https://stock.paul-learning.dev`（custom subdomain via DNS CNAME）。

> 註：repo 原本是「股市指標儀表板」，已全面改版為跟單追蹤器。`stock_dashboard.db`、`stock-dashboard.service` 等沿用舊名以減少 infra 變動。

## 命名由來

**Publixia** /pʌbˈlɪk-si-ə/ 是一個結合「古羅馬歷史底蘊」與「現代軟體自動化」的自創詞：

1. **歷史溯源 — Publicani（羅馬稅收承包商）**：人類最早的「法人組織」與「股份持有者」原型，借此表達回歸交易本質的精神。
2. **字根拆解**：`Publi-`（Public 公開市場／Publish 發布）、`-ix`（Index 指標／Execute 執行）、`-ia`（領域／系統）。
3. **功能轉譯 — The Public Market's Execution Axis**：從公開資訊中過濾出精確的交易信號。

定位一句話：**「追蹤公開市場上的聰明錢，用 AI 把名人的一買一賣整理成可跟單的信號。」**

## 這個產品在做什麼

1. **抓貼文** — 用 [Scrapling](https://github.com/D4Vinci/Scrapling) 的隱身瀏覽器無登入爬追蹤對象的 Threads（捲動 + 攔截 GraphQL XHR，從內嵌 JSON 取 shortcode / 文字 / 時間）。
2. **AI 解析** — 把貼文丟給 Cloudflare Workers AI，抽出個股買賣訊號（買/賣/續抱/看多/看空，有寫到就記價格/張數），大盤（台股/加權）對應到加權指數。
3. **正規化** — 中文名/暱稱/代號 → 正式 `(ticker, market)`（台股來自 FinMind、美股靜態表、加權指數）。
4. **股價追蹤** — 用 yfinance 算每檔標的「從貼文當下買入」的最新 / 7日 / 1月漲跌幅。
5. **呈現** — 前端一條混合所有人的時間軸，每篇標作者（依人配色）、內嵌交易色票、右側標代號/股名/漲跌幅；可依人物 + 「有提到股票」組合篩選。
6. **通知** — 偵測到新交易發 Discord。

目前追蹤對象（data-driven，在 `tracked_accounts` 表）：爸逆逆（Threads `@ajhsu0820`）、巴逆逆（Threads `@banini31`）。

## Repository layout

```
backend/                 FastAPI app + scrapers + AI 解析 + 排程 + DB layer
frontend/                Vite/React app（時間軸 + 篩選 + 個人頁）
tests/                   pytest backend test suite（從 repo root 跑）
worker/foreign-flow-ai/  舊產品的 Cloudflare Worker，已 dormant（無人呼叫）
stock-dashboard.service  systemd unit copied to VPS
deploy.sh                Manual VPS deploy（CI 外的後備）
.github/workflows/       CI: deploy-backend.yml, deploy-frontend.yml, deploy-worker.yml
```

## 後端架構

分層：**scrapers → repositories → services → routes**，APScheduler 驅動定時 job。

- `scrapers/`（`base`, `threads`, `runner`）— Scrapling 爬取；增量模式：已存貼文淺捲 + 捲到已看過就提前停，首次才深捲回補。
- `repositories/`（`tracked_accounts`, `posts`, `trades`, `stock_reference`, `price_tracking`, `scheduler`）— SQLite，全 upsert。
- `services/` — `trade_extraction`（prompt + 容錯 JSON 解析）、`normalization`、`extraction_runner`、`stock_reference_sync`、`price_history` + `price_tracking_runner`、`backup`。
- `core/cloudflare_ai.py` — 直接呼叫 Workers AI REST API；`core/discord.py`。
- `db/runner.py` — forward-only migration runner，`init_db()` 每次啟動套用。

## 排程 jobs（`backend/jobs/registry.py`；實際 cron 存在 `scheduler_jobs` 表，TZ = Asia/Taipei）

| job | 預設 cron | 說明 |
|---|---|---|
| `scrape_accounts` | `*/30 * * * *` | 抓追蹤帳號新貼文 |
| `extract_trades`  | `5,35 * * * *` | AI 解析買賣訊號（含舊 prompt 版本重抽） |
| `stock_ref_sync`  | `0 7 * * *`    | 同步台股/美股代號 + 加權指數 |
| `price_tracking`  | `0 */6 * * *`  | 算最新/7日/1月漲跌幅 |
| `backup_db`       | `0 3 * * *`    | SQLite 上傳 Cloudflare R2 |

## 資料表

| 表 | 內容 |
|---|---|
| `tracked_accounts` | 追蹤的人 + 其社群帳號（data-driven，`person_key` 分群多平台） |
| `posts` | 每篇爬到的貼文，`(platform, platform_post_id)` 去重；`extraction_status` 驅動解析佇列 |
| `extracted_trades` | 每篇貼文 AI 抽出的 0..N 筆交易；重抽採整篇取代 |
| `stock_reference` | 名稱/暱稱/代號 → `(ticker, market)`；含加權指數（market `INDEX`） |
| `trade_price_tracking` | 每篇×每檔的進場價與最新/7日/1月收盤與漲跌幅 |

## GitHub Secrets

**Settings → Secrets and variables → Actions**：

| Secret | Used by | What it is |
|---|---|---|
| `VPS_HOST` / `VPS_SSH_KEY` | `deploy-backend.yml` | VPS 位址 + root 私鑰 |
| `CLOUDFLARE_ACCOUNT_ID` | `deploy-backend.yml` | Workers AI 的 account id |
| `CLOUDFLARE_API_TOKEN` | `deploy-backend.yml` | 呼叫 Workers AI 的 token — **必須包含「Workers AI」權限**（Read 即可跑推論）。只有部署 Worker 的 token 會回 403 |
| `DISCORD_STOCK_WEBHOOK_URL` | `deploy-backend.yml` | 新交易通知 webhook |
| `FINMIND_TOKEN` | `deploy-backend.yml` | 同步台股代號表 |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_ENDPOINT_URL` / `R2_BUCKET` | `deploy-backend.yml` | DB 備份 |

> 後端讀的 env 名稱是 `CF_ACCOUNT_ID` / `CF_API_TOKEN` / `DISCORD_COPYTRADE_WEBHOOK_URL`；deploy workflow 會把上述 secrets 對應過去。沒設 `CF_*` 時，爬蟲仍會抓貼文，只是解析會錯、不會有交易色票。

GitHub Pages 需設 **Settings → Pages → Source = GitHub Actions**。

## VPS environment variables

`stock-dashboard.service` 讀 `/opt/stock-dashboard/backend/.env`。`deploy-backend.yml` 每次部署都從 Secrets 重寫 `.env`，手動加的會被覆蓋——要持久請加成 Secret。後端部署時也會跑 `scrapling install` 抓爬蟲用的瀏覽器。

## DB migrations

Schema 變更放 `backend/db/migrations/NNNN_<snake_name>.sql`（4 碼、forward-only）。runner（`backend/db/runner.py`）啟動時套用未跑過的 migration，記在 `schema_migrations`。已部署的 migration 視為不可變——要修正請開新 migration，不要改舊的。

## 本機開發

```bash
# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/scrapling install        # 一次性：抓 Scrapling 用的隱身瀏覽器
.venv/bin/uvicorn main:app --reload --port 8000

# Frontend（另一個 terminal）
cd frontend
npm install
npm run dev   # http://localhost:5173，vite proxy /api → :8000
```

測試（都不需網路/瀏覽器——爬蟲與 AI 用 fixture + mock）：

```bash
python3 -m pytest tests/      # backend（conftest 用 :memory: DB）
cd frontend && npm test       # frontend（vitest + MSW）
```

沒有憑證也想試真實 Workers AI 解析：在 `backend/.env`（gitignored）填 `CF_ACCOUNT_ID` / `CF_API_TOKEN`，跑 `backend/.venv/bin/python scripts/check_cf_ai.py`。
