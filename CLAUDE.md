# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Repository overview

Personal **大盤成交金額冷熱判讀** tracker. It syncs daily 指數收盤 + 量能 for two
markets (台股加權 via TWSE, Nasdaq Composite via Yahoo), derives a 冷熱 reading
from each, shows them on a single page behind a market tab switcher, and pushes a
盤中 reading (台股 only) to Discord each trading day. Single product, single VPS
service:
- `backend/` — FastAPI app + APScheduler + SQLite (`stock_dashboard.db`), on the VPS
- `frontend/` — Vite + React + Tailwind, deployed to GitHub Pages on the custom subdomain `stock.paul-learning.dev` (no path prefix — served from `/`)
- `tests/` — pytest suite for the backend (run from repo root: `python3 -m pytest tests/`)

(The repo was pivoted twice: first from a TWSE indicators dashboard, then from a
Threads copy-trading tracker. `stock_dashboard.db` and `stock-dashboard.service`
keep their old names to avoid churn.)

## Running locally

```bash
# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # http://localhost:5173, vite proxies /api → :8000
```

Test suites (both run with no network — TWSE is exercised via fixtures + mocks):
```bash
python3 -m pytest tests/                    # backend (conftest sets DB_PATH=:memory:)
cd frontend && npm test                     # frontend (vitest + MSW)
```

## Backend architecture

Layered: **core (fetchers) → repositories → services → routes**, with APScheduler driving the periodic jobs.

- `backend/main.py` — FastAPI app (`Market Heat API`), registers `api/routes/market.py`.
- `backend/scheduler.py` + `backend/jobs/registry.py` — APScheduler in TST, DB-driven. `JOBS` is the name → callable + default-cron map; rows are seeded into `scheduler_jobs` on startup (insert-if-missing), and edits to that table take effect on the next restart. Jobs: `intraday_heat_signal` (`0 13 * * 1-5`, 盤中判讀推 Discord), `market_volume_sync` (`0 16 * * 1-5`, TWSE 收盤後), `nasdaq_volume_sync` (`0 6 * * 2-6`, 美股 16:00 ET 收盤後，夏令/冬令都涵蓋), `backup_db` (`0 3`).
- `backend/core/markets.py` — the `TW`/`US` market codes. Everything downstream (repo, services, API) is market-scoped; there is deliberately no "all markets" query, since the two calendars and turnover units differ.
- `backend/core/twse.py` — FMTQIK 收盤月報 (the authoritative daily rows). `core/twse_intraday.py` — 盤中快照 via MIS 即時行情 (`getStockInfo.jsp` 指數 + `getStatis.jsp` 累計成交金額), falling back to FMTQIK when MIS has nothing for today. `core/nasdaq.py` — Yahoo chart endpoint (`^IXIC`), one request for the whole range (see 兩個市場的量能不是同一種東西 below). `core/discord.py` — `send_to_discord`. `core/alerts.py` — `send_alert` (維運通報, see 失敗一定要有聲音 below).
- `backend/services/` — `market_volume_sync.py` (two entry points: `run_market_volume_sync` TWSE 月報式增量, `run_nasdaq_volume_sync` Yahoo 單請求 + 10 天重疊視窗; empty table backfills from 2016, or hit `POST /api/market/volume-heat/refresh?market=…`), `market_heat.py` (冷熱判讀 — ln量能 vs ln指數 OLS 位階常態 → 殘差近一年百分位 → 五級判讀, all derived on read, market-agnostic), `intraday_heat.py` (盤中快照 → 線性外推全日成交金額 → 判讀 → Discord, **台股 only**), `backup.py` (SQLite → R2).
- `backend/db/runner.py` — forward-only migration runner; `init_db()` runs on every startup.

### 失敗一定要有聲音 (`core/alerts.py`)

**沒有靜默失敗。** 排程一天只跑一次，「安靜跳過」和「成功」在 Discord 上長得一模一樣，
壞掉可以壞很多天沒人發現 —— 盤中判讀第一次上線那天就是這樣沒聲沒息地跳過。所以：

- `scheduler._wrap` 攔到任何例外 → `record_run(error)` + `send_alert` 推 🚨，訊息帶
  job 名稱、cron、例外類型/訊息，非領域例外還附 traceback 尾巴。開機時 cron 解析
  失敗（那支 job 永遠不會跑）也推一則。
- 服務層跑不出結果時**往上拋，不要 return 一個安靜的 dict**，並把定位資訊寫進例外
  訊息裡（實際欄位、`rtcode`/`rtmessage`、有幾列資料、該檢查哪個環境變數）——
  通報就只有這句話可以看。
- 唯一的例外是休市：丟 `MarketClosed`（`FetcherError` 的子類），呼叫端推一則低調的
  ℹ️ 說明今天為什麼沒判讀。所以 Discord 上「什麼都沒有」永遠只代表 job 沒跑到。
- Webhook 順序 `DISCORD_OPS_WEBHOOK_URL` → market → stock，空字串視同未設定（未設定的
  GitHub secret 會被 deploy 寫成空值）。設第一支就能把維運噪音跟判讀分頻道。
- `send_alert` 自己絕不往外丟例外，推不出去時把整則內容寫進 log。

### 兩個市場的量能不是同一種東西

`market_volume_daily.turnover` 的單位隨 `market` 而異，**這是刻意的**：

- `TW` → 成交金額（億元），TWSE FMTQIK
- `US` → 成交股數（億股，Nasdaq composite volume），Yahoo `^IXIC`

美股沒有免費而穩定的「全市場成交金額」日資料源，而 composite volume 在美股語境
裡本來就是指股數。之所以無妨：`ln(成交金額) ≈ ln(成交股數) + ln(成交均價)`，均價
大致隨指數等比例走，所以在 `ln(量) ~ ln(指數)` 的迴歸裡換成股數只是把斜率平移約
1，**殘差幾乎不變** —— 而判讀吃的就是殘差。兩個市場各自迴歸、各自排百分位，從不
跨市場比較，所以單位不同不會互相污染。

配對挑 Nasdaq Composite 指數 + Nasdaq 上市股票 composite volume，是因為指數與量能
**來自同一個宇宙**。美股的成交量是碎的（NYSE / Nasdaq / Cboe / IEX + 約四成
off-exchange），拿 S&P 500 配全市場量是在比兩個不同的東西。要換資料源時先確認這
一點還成立。

`core/nasdaq.py` 的護欄（成交股數 1–1,000 億股、指數 100–1,000,000）擋的不是「今天
量特別大」而是「單位或欄位變了」—— 真的收到成交金額會落在 1000 億以上被擋下來。
endpoint 曾用 GitHub Actions runner 實測過（2016-01-04 起 2,661 列，量能
min 7.7 / max 182.9 / mean 44.8 億股），沙箱本身連不到 finance 類 host。

### 盤中判讀 (`services/intraday_heat.py`)

**台股專屬，不要移植到美股。** 美股的量能是明顯的 U 型，收盤競價（MOC）常常一根
就吃掉全日一成以上，線性外推在收盤前會系統性低估到把正常日讀成偏冷。真要做得先
換成經驗型盤中量能曲線（近 N 日的「每分鐘累計佔全日比例」查表）。

Runs at 13:00 TST, half an hour before the 13:30 close. Takes the MIS snapshot's
cumulative turnover, **linearly extrapolates** it over the 09:00–13:30 session
(at 13:00 that is ×1.125), feeds the estimate through the same `market_heat`
regression, and posts the reading to Discord labelled as an estimate.

Two things to preserve when touching it:
- It **must not write to `market_volume_daily`**. An estimated row would show up
  in the frontend as a real bar until the 16:00 sync overwrites it.
- `core/twse_intraday.py` guards the turnover magnitude (10–100,000 億元) and
  raises with the actual response keys when MIS's 成交金額 field is missing —
  a silently wrong unit is worse than a missing reading. **The MIS 大盤統計
  endpoint/field (`getStatis.jsp` → `tm`) has not been verified against a live
  session**; `fetch_snapshot` raises (never returns `None`) so the failure
  reason reaches Discord — 空 `msgArray` 會連 `rtcode`/`rtmessage` 一起報，那正是
  MIS 講「你沒有 session」的地方。修的時候就改這一個模組。

## Frontend architecture

Single minimal page: 大盤成交金額冷熱判讀.

- `frontend/vite.config.ts` — `base: '/'` (served from a subdomain root); `frontend/src/router.tsx` — react-router without basename: `/` → `MarketHeatPage`, everything else redirects home.
- `MarketHeatPage` (`/`) = **market tabs** (台股大盤 / Nasdaq, from `src/lib/markets.ts` — that file owns every per-market label: 指數/量能 的稱呼與單位, so components take a `MarketConfig` prop instead of hardcoding 加權指數/成交金額/億) + range tabs (近一月/近一季/近半年/近一年/全部, in trading days; 全部 omits `days`) + a 半年區間 dropdown (2026 上 / 2025 下 / … down to 2016 上; picking one fetches the full history — same query key as 全部 — and slices client-side via `src/lib/half-year.ts`, since the API only takes 近 N 日. Tabs and dropdown are mutually exclusive; the 今日判讀 card then shows that half's last trading day) + `MarketHeat` (今日判讀 card, 冷熱 meter, scrollable 成交金額 bar chart vs 位階常態 dashed line) + `IndexChart` (大盤位階 vs 量能判讀: 加權指數 line, one 判讀-colored dot per day) + `HeatTable` (the Google Sheet 比較表: same columns/判讀 wording, newest first).
- `MethodPage` (`/method`) — the derivation written out (why a flat average misreads, the OLS 位階常態, 量能比/殘差, 近一年百分位, the five bands) plus data source and an explicit note on why numbers drift from the source spreadsheet (its coefficients are frozen; ours refit each read). Keep it in sync when the method changes.
- API client (`src/lib/api-client.ts`) reads `import.meta.env.PROD` to switch dev (relative `/api`) vs prod (`https://api.paul-learning.dev`). Data hook: `src/hooks/useMarketHeat.ts`; level colors/labels in `src/lib/market-heat.ts` (diverging blue↔red, 判讀 always printed next to color).

## Deployment

- **Push to master** triggers the relevant GitHub Action by path:
  - `frontend/**` → `deploy-frontend.yml` → GitHub Pages
  - `backend/**` or `stock-dashboard.service` → `deploy-backend.yml` → pytest gate → rsync to VPS → `pip install` → systemd restart
- VPS path is fixed at `/opt/stock-dashboard/`; decoupled from the repo name.
- `init_db()` runs every backend startup → migrations are auto-applied.
- Manual deploy fallback: `./deploy.sh` from repo root (requires `VPS_HOST` env var).

## Secrets

Stored in GitHub Actions, written into `/opt/stock-dashboard/backend/.env` on every backend deploy (hand-edits on the VPS are overwritten on next push — add to Secrets to persist). Current set: `R2_*` (DB backup), `DISCORD_STOCK_WEBHOOK_URL` (written as `DISCORD_MARKET_WEBHOOK_URL`, 盤中判讀 推播), and the optional `DISCORD_OPS_WEBHOOK_URL` (維運通報; unset → alerts fall back to the 判讀 webhook). Without any webhook the 盤中 job raises and the alert content is written to the log instead.

**Never commit secrets** (API tokens, webhooks, VPS hostname, SSH keys, `.env`). If something slips into a commit, rotate the secret — `git push --force` doesn't undo what's already been copied elsewhere.

## DB schema gotchas

- The live table is `market_volume_daily` (migrations `0034` + `0036`): one row per (market, trading day), upserted on `(market, date)`. `0036` added the `market` column and renamed `taiex_close` → `index_close` (the column now also holds Nasdaq closes). Everything the UI shows is derived from it on read — no computed values are persisted.
- Migration `0022` **dropped all old dashboard tables** (indicator/futures/institutional/etc.). It's destructive and runs on startup — the only safety net for the old data is the nightly R2 backup. Don't resurrect those tables.
- The copy-trading tables (`tracked_accounts`, `posts`, `extracted_trades`, `stock_reference`, price-tracking) are **orphaned but intentionally still there**: the code that read them was removed, the tables were not (a DROP is unrecoverable). Migration `0035` only cleared their `scheduler_jobs` rows. Don't wire anything new to them; drop them deliberately if the data is confirmed unwanted.
