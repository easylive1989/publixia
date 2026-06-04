# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Repository overview

Personal **copy-trading tracker**. It scrapes the Threads posts of a few tracked
people, uses AI to extract which stocks they bought/sold, and shows it per
person. Single product, single VPS service:
- `backend/` — FastAPI app + APScheduler + SQLite (`stock_dashboard.db`) + Scrapling scrapers + Cloudflare Workers AI extraction, on the VPS
- `frontend/` — Vite + React + Tailwind, deployed to GitHub Pages on the custom subdomain `stock.paul-learning.dev` (no path prefix — served from `/`)
- `tests/` — pytest suite for the backend (run from repo root: `python3 -m pytest tests/`)
- `worker/foreign-flow-ai/` — a Cloudflare Worker from the previous (stock-dashboard) product. **Dormant** — nothing calls it anymore; left in place, not part of the current flow.

(The repo was pivoted from a TWSE indicators dashboard; `stock_dashboard.db` and `stock-dashboard.service` keep their old names to avoid churn.)

## Running locally

```bash
# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/scrapling install        # one-time: fetch the stealth browser Scrapling drives
.venv/bin/uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # http://localhost:5173, vite proxies /api → :8000
```

Test suites (both run with no network / no browser — scrapers and AI are exercised via fixtures + mocks):
```bash
python3 -m pytest tests/                    # backend (conftest sets DB_PATH=:memory:)
cd frontend && npm test                     # frontend (vitest + MSW)
```

## Backend architecture

Layered: **scrapers → repositories → services → routes**, with APScheduler driving the periodic jobs.

- `backend/main.py` — FastAPI app (`Copy-Trading Tracker API`), registers `api/routes/people.py`.
- `backend/scheduler.py` + `backend/jobs/registry.py` — APScheduler in TST, DB-driven. `JOBS` is the name → callable + default-cron map; rows are seeded into `scheduler_jobs` on startup (insert-if-missing), and edits to that table take effect on the next restart. Jobs: `scrape_accounts` (`*/30`), `extract_trades` (`5,35 * * * *`, just after each scrape), `stock_ref_sync` (`0 7`), `backup_db` (`0 3`).
- `backend/scrapers/` — Scrapling-based. `threads.py` drives a stealth browser (`StealthyFetcher`), scrolls to lazy-load history, and parses posts from BOTH the inline `data-sjs` JSON and captured `/graphql` XHR (post `code` / `caption.text` / `taken_at`). Logged-out works for public profiles; `tracked_accounts.session_cookie` is an optional per-account fallback if a profile gets gated. `runner.py` picks a scraper by `platform` and upserts posts. **Don't** parse Threads HTML with brittle CSS — the embedded JSON is the stable source.
- `backend/repositories/` — SQLite access, all **upserts**: `posts` on `(platform, platform_post_id)` (returns `is_new`); `extracted_trades` on `(post_id, raw_symbol, direction)`; `stock_reference` on `(market, ticker)`; `tracked_accounts` on `(platform, handle)`.
- `backend/services/` — `trade_extraction.py` (Cloudflare Workers AI + JSON schema + pydantic validation; `PROMPT_VERSION`), `normalization.py` (raw stock string → canonical `(ticker, market)`), `extraction_runner.py` (drains pending posts → extract → normalize → save → Discord notify on the pending→done transition only), `stock_reference_sync.py` (TW roster from FinMind + a curated US static map), `backup.py` (SQLite → R2).
- `backend/core/cloudflare_ai.py` — calls the Workers AI REST API directly (`/accounts/{id}/ai/run/{model}`). `core/discord.py` — `send_to_discord`.
- `backend/db/runner.py` — forward-only migration runner; `init_db()` runs on every startup.

## Frontend architecture

- `frontend/vite.config.ts` — `base: '/'` (served from a subdomain root); `frontend/src/router.tsx` — react-router without basename: `/` (HomePage) + `/people/:personKey` (PersonProfilePage).
- API client (`src/lib/api-client.ts`) reads `import.meta.env.PROD` to switch dev (relative `/api`) vs prod (`https://api.paul-learning.dev`). Data hooks live in `src/hooks/usePeople.ts`.
- Design: editorial/finance look — Fraunces (display) + IBM Plex Mono (tickers) + Noto Sans TC (body), warm-paper theme, direction-coded `TradeChip`. Tokens in `src/index.css`, fonts via a Google Fonts `@import`.
- `posted_at` from the backend is **naive-UTC ISO** (no zone) — pass it through `asUtc()` (in `src/lib/relative-time.ts`) before `new Date()` so it isn't parsed as local time.

## Deployment

- **Push to master** triggers the relevant GitHub Action by path:
  - `frontend/**` → `deploy-frontend.yml` → GitHub Pages
  - `backend/**` or `stock-dashboard.service` → `deploy-backend.yml` → pytest gate → rsync to VPS → `pip install` → `scrapling install` (fetch browser, non-fatal) → systemd restart
  - `worker/**` → `deploy-worker.yml` (the dormant worker; rarely needed)
- VPS path is fixed at `/opt/stock-dashboard/`; decoupled from the repo name.
- `init_db()` runs every backend startup → migrations are auto-applied.
- Manual deploy fallback: `./deploy.sh` from repo root (requires `VPS_HOST` env var).

## Secrets

Stored in GitHub Actions, written into `/opt/stock-dashboard/backend/.env` on every backend deploy (hand-edits on the VPS are overwritten on next push — add to Secrets to persist). Current set: `FINMIND_TOKEN` (stock list), `R2_*` (DB backup), `CF_ACCOUNT_ID` / `CF_API_TOKEN` / `CF_AI_MODEL` (Workers AI extraction), `DISCORD_COPYTRADE_WEBHOOK_URL` (new-trade notifications). Without the `CF_*` secrets, scraping still populates posts but extraction errors out (caught) and no trade chips appear.

**Never commit secrets** (API tokens, webhooks, VPS hostname, SSH keys, `.env`). If something slips into a commit, rotate the secret — `git push --force` doesn't undo what's already been copied elsewhere.

## DB schema gotchas

- Core tables (migration 0023): `tracked_accounts`, `posts`, `extracted_trades`, `stock_reference`. Every write path must use the upsert keys above (enforced by UNIQUE constraints). `posts.extraction_status` (`pending|done|error|skipped`) is the extraction work queue.
- Migration `0022` **dropped all old dashboard tables** (indicator/futures/institutional/etc.). It's destructive and runs on startup — the only safety net for the old data is the nightly R2 backup. Don't resurrect those tables.
- Tracked accounts are **data-driven** (seeded in migration `0024`: 爸逆逆 `@ajhsu0820`, 巴逆逆 `@banini31`). Add a person by inserting a `tracked_accounts` row, not by hardcoding.
- `purge_old_data` (in `db/__init__.py`) prunes posts older than 3 years but is **not currently wired into the scheduler** — call it manually or add a cleanup job if retention becomes a concern.
