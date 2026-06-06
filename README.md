# Publixia — 對帳中 · Call For Money（跟單對帳計分板）

追蹤特定人物的社群貼文與 podcast，用 AI 解析出他們買賣了哪些股票，依「跟單損益」幫每位老師打分數排名——一個運動轉播風的**對帳計分板**：戰績排行榜 + 喊單實況逐筆對帳。

- **Backend**: FastAPI on a VPS at `/opt/stock-dashboard/backend`, deployed via `.github/workflows/deploy-backend.yml`. Service: `stock-dashboard.service` (systemd). API: `https://api.paul-learning.dev`.
- **Frontend**: Vite + React + Tailwind（運動轉播風計分板），deployed to GitHub Pages via `.github/workflows/deploy-frontend.yml`. Public URL: `https://stock.paul-learning.dev`（custom subdomain via DNS CNAME）。

> 註：repo 原本是「股市指標儀表板」，後改為跟單追蹤器，現為對帳計分板。`stock_dashboard.db`、`stock-dashboard.service` 等沿用舊名以減少 infra 變動。

## 命名由來

**Publixia** /pʌbˈlɪk-si-ə/ 是一個結合「古羅馬歷史底蘊」與「現代軟體自動化」的自創詞：

1. **歷史溯源 — Publicani（羅馬稅收承包商）**：人類最早的「法人組織」與「股份持有者」原型，借此表達回歸交易本質的精神。
2. **字根拆解**：`Publi-`（Public 公開市場／Publish 發布）、`-ix`（Index 指標／Execute 執行）、`-ia`（領域／系統）。
3. **功能轉譯 — The Public Market's Execution Axis**：從公開資訊中過濾出精確的交易信號。

定位一句話：**「追蹤公開市場上的聰明錢，用 AI 把名人的一買一賣整理成可跟單的信號，再逐筆對帳打分。」**

## 這個產品在做什麼

1. **抓內容** — Threads 貼文用 [Scrapling](https://github.com/D4Vinci/Scrapling) 隱身瀏覽器無登入爬（捲動 + 攔截 GraphQL XHR）；Podcast 用 RSS（`feedparser`）取音檔 / 標題 / 時間。
2. **轉逐字稿（podcast）** — 下載音檔 → ffmpeg 轉 16k 單聲道 → Groq Whisper 轉文字 → OpenCC 簡轉繁；節目可設專屬 prompt 改善專有名詞。RSS 有附逐字稿則直接用。文字平台略過此步。
3. **AI 解析** — 把內容丟給 Cloudflare Workers AI，抽出個股買賣訊號（買/賣/續抱/看多/看空，有寫到就記價格/張數），大盤對應加權指數。
4. **正規化** — 中文名/暱稱/代號 → 正式 `(ticker, market)`（台股來自 FinMind、美股 SEC + 別名表、加權指數；比對大小寫不敏感、相容處置股星號與主動式 ETF 簡寫）。
5. **股價追蹤** — 用 yfinance 算每檔標的「從貼文當下進場」的最新 / 7日 / 1月漲跌幅。
6. **對帳計分** — 依規則算每位老師戰績：做多看漲賺、賣出看跌賺，跟單損益（用最新價）≥0 即命中；輸出命中率 / 累積損益（逐筆加總）/ 近 5 場，依累積損益排名（無喊單者列 DNP）。
7. **呈現** — 前端「對帳中」計分板：**戰績排行榜**（W–L / 命中率 / 累積損益 / 近5場）+ **喊單實況**（每則逐筆判 跟單賺 / 住套房 / 賣對了 / 追蹤中）；可點老師原地篩選、只看喊單。
8. **通知** — 偵測到新交易發 Discord。

目前追蹤對象（data-driven，在 `tracked_accounts` 表）：爸逆逆（Threads `@ajhsu0820`）、巴逆逆（Threads `@banini31`）、Aoi（Threads）、股癌（Podcast，SoundOn RSS）。

## Repository layout

```
backend/                 FastAPI app + scrapers + 轉錄 + AI 解析 + 排程 + DB layer
frontend/                Vite/React app（對帳計分板：戰績排行榜 + 喊單實況）
tests/                   pytest backend test suite（從 repo root 跑）
.claude/skills/          專案 skill（fix-trade-signal：手動修正標錯/漏抓的交易）
docs/design/             Claude Design handoff（計分板設計稿原檔）
stock-dashboard.service  systemd unit copied to VPS
deploy.sh                Manual VPS deploy（CI 外的後備）
.github/workflows/       CI: deploy-backend.yml, deploy-frontend.yml
```

## 後端架構

分層：**scrapers → repositories → services → routes**，APScheduler 驅動定時 job。

- `scrapers/`（`base`, `threads`, `podcast`, `runner`）— `_SCRAPERS` 依平台分派；Threads 走 Scrapling 增量爬，Podcast 走 RSS。
- `repositories/`（`tracked_accounts`, `posts`, `trades`, `stock_reference`, `price_tracking`, `scoreboard`, `scheduler`）— SQLite，全 upsert。
- `services/` — `trade_extraction`（prompt + 容錯 JSON 解析 + 長逐字稿分塊）、`transcription` / `transcription_runner`（RSS 優先→Groq）、`core/chinese`（OpenCC 簡轉繁）、`normalization`、`extraction_runner`、`stock_reference_sync`、`price_history` + `price_tracking_runner`、`scoreboard`（戰績聚合）、`backfill_*`、`backup`。
- `core/cloudflare_ai.py`（Workers AI）、`core/groq_ai.py`（Whisper）、`core/discord.py`。
- `db/runner.py` — forward-only migration runner，`init_db()` 每次啟動套用。

主要 API：`GET /api/timeline`（喊單實況 feed）、`GET /api/people`、`GET /api/scoreboard`（戰績排行榜）。

## 排程 jobs（`backend/jobs/registry.py`；實際 cron 存在 `scheduler_jobs` 表，TZ = Asia/Taipei）

| job | 預設 cron | 說明 |
|---|---|---|
| `scrape_accounts`    | `*/30 * * * *`  | 抓追蹤帳號新貼文 / podcast 集數 |
| `transcribe_podcasts`| `10,40 * * * *` | 下載 podcast 音檔轉逐字稿（最新優先） |
| `extract_trades`     | `5,35 * * * *`  | AI 解析買賣訊號，接著更新價格追蹤 |
| `stock_ref_sync`     | `0 7 * * *`     | 同步台股/美股代號 + 加權指數，再重抽未對上的標的 |
| `backup_db`          | `0 3 * * *`     | SQLite 上傳 Cloudflare R2 |

> 價格追蹤沒有獨立 cron——它在 `extract_trades`、`stock_ref_sync` 之後與每次啟動時跑。
> Prompt 升級**不會**自動重抽舊貼文（stale 重抽已停用），手動修正才不會被覆蓋；要全面重跑需手動 re-queue。

## 資料表

| 表 | 內容 |
|---|---|
| `tracked_accounts` | 追蹤的人 + 其社群/podcast 帳號（`person_key` 分群多平台；podcast 的 RSS 放 `profile_url`、可設 `transcribe_prompt`） |
| `posts` | 每篇貼文/集數，`(platform, platform_post_id)` 去重；`extraction_status` 驅動解析佇列；podcast 另有 `audio_url`/`transcript_url`/`transcript_status`/`title` |
| `extracted_trades` | 每篇 AI 抽出的 0..N 筆交易；重抽採整篇取代 |
| `stock_reference` | 名稱/暱稱/代號 → `(ticker, market)`；含加權指數（market `INDEX`） |
| `trade_price_tracking` | 每篇×每檔的進場價與最新/7日/1月收盤與漲跌幅 |

> 戰績排行榜是**即時聚合算出來的**（`services/scoreboard.py`），不另存表。

## 手動修正標錯/漏抓的交易

`.claude/skills/fix-trade-signal/` 是專案 skill：當某則貼文的訊號被 AI 標錯或漏抓，直接說「這單標錯了 / 漏抓了 X / 方向反了」，它會問清楚是哪一則、SSH 進 VPS 定位，確認後改 `extracted_trades`（走 normalize + 重算價格追蹤）。因 stale 重抽已停用，手動修正會長存。

## GitHub Secrets

**Settings → Secrets and variables → Actions**：

| Secret | Used by | What it is |
|---|---|---|
| `VPS_HOST` / `VPS_SSH_KEY` | `deploy-backend.yml` | VPS 位址 + root 私鑰 |
| `CLOUDFLARE_ACCOUNT_ID` | `deploy-backend.yml` | Workers AI 的 account id |
| `CLOUDFLARE_API_TOKEN` | `deploy-backend.yml` | 呼叫 Workers AI 的 token — **必須包含「Workers AI」權限**。只有部署 Worker 的 token 會回 403 |
| `GROQ_API_KEY` | `deploy-backend.yml` | Groq Whisper（podcast 轉逐字稿）；免費 tier 足夠 |
| `DISCORD_STOCK_WEBHOOK_URL` | `deploy-backend.yml` | 新交易通知 webhook |
| `FINMIND_TOKEN` | `deploy-backend.yml` | 同步台股代號表 |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_ENDPOINT_URL` / `R2_BUCKET` | `deploy-backend.yml` | DB 備份 |

> 後端讀的 env 名稱是 `CF_ACCOUNT_ID` / `CF_API_TOKEN` / `GROQ_API_KEY` / `DISCORD_COPYTRADE_WEBHOOK_URL`；deploy workflow 會把上述 secrets 對應過去。沒設 `CF_*` 時，爬蟲仍會抓貼文，只是解析會錯、不會有交易；沒設 `GROQ_API_KEY` 時，podcast 會抓進來但轉錄會失敗。

GitHub Pages 需設 **Settings → Pages → Source = GitHub Actions**。

## VPS environment variables

`stock-dashboard.service` 讀 `/opt/stock-dashboard/backend/.env`。`deploy-backend.yml` 每次部署都從 Secrets 重寫 `.env`，手動加的會被覆蓋——要持久請加成 Secret。後端部署時也會跑 `scrapling install`（爬蟲瀏覽器）並安裝 `ffmpeg`（podcast 轉檔）。

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
# podcast 本機轉錄另需 ffmpeg（brew install ffmpeg）

# Frontend（另一個 terminal）
cd frontend
npm install
npm run dev   # http://localhost:5173，vite proxy /api → :8000
```

測試（都不需網路/瀏覽器——爬蟲、AI、轉錄用 fixture + mock）：

```bash
python3 -m pytest tests/      # backend（conftest 用 :memory: DB）
cd frontend && npm test       # frontend（vitest + MSW）
```
