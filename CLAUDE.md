# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Repository overview

Personal stock dashboard. Single product, single VPS service:
- `backend/` — FastAPI app + APScheduler-based fetchers + SQLite (`stock_dashboard.db`) on the VPS
- `frontend/` — Vite + React + Tailwind, deployed to GitHub Pages on the custom subdomain `stock.paul-learning.dev` (no path prefix — served from `/`)
- `tests/` — pytest suite for the backend (run from repo root: `python3 -m pytest tests/`)

There is no monorepo / no shared `common/` package — `core/discord.py` is the only Discord helper.

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

Test suites:
```bash
python3 -m pytest tests/                    # backend
cd frontend && npm test                     # frontend (vitest)
```

## Backend architecture

- `backend/main.py` — FastAPI app, registers route modules under `api/routes/`.
- `backend/scheduler.py` — APScheduler in TST. **All snapshots are daily** — TWSE-related fetchers run at 14:00 TST, US + FX at 06:00 TST. Don't reintroduce intraday fetches; the data model assumes one row per `(key, trade_date)`.
- `backend/fetchers/` — yfinance + FinMind + scraper modules. `_fetch_price` returns the trade date alongside the close, so writes on holidays upsert the prior trading day's row instead of fabricating a new one.
- `backend/repositories/` — SQLite access. `save_indicator` / `save_stock_snapshot` are **upserts** keyed on `(indicator/ticker, date)` — schema enforces this via UNIQUE INDEX (migration 0005).
- `backend/db/runner.py` — forward-only migration runner; baseline mechanism handles legacy DBs that pre-date the runner.
- `backend/services/alert_notifier.py`, `backend/services/token_service.py` — both use `core/discord.py` `send_to_discord`.

## Frontend architecture

- `frontend/vite.config.ts` — `base: '/'` (served from a subdomain root).
- `frontend/src/router.tsx` — react-router without basename.
- API client reads `import.meta.env.PROD` to switch between dev (relative `/api`) and prod (`https://api.paul-learning.dev`).
- Sparkline components: data points are one per trading day. Don't add interpolation/gap-filling — non-trading days should be visually absent.

## Deployment

- **Push to master** triggers the relevant GitHub Action by path:
  - `frontend/**` → `deploy-frontend.yml` → GitHub Pages
  - `backend/**` or `stock-dashboard.service` → `deploy-backend.yml` → rsync to VPS + systemd restart
  - `admin/**` → `deploy-admin.yml` → rsync admin CLI to VPS + refresh `admin/.venv` (no service restart; admin CLI is interactive, not a daemon)
- VPS path is fixed at `/opt/stock-dashboard/`; this is decoupled from the repo name.
- `init_db()` runs every backend startup → migrations are auto-applied.
- Manual deploy fallback: `./deploy.sh` from repo root (requires `VPS_HOST` env var).

## Secrets

Secrets are stored in GitHub Actions and written into `/opt/stock-dashboard/backend/.env` on every backend deploy. Editing the file by hand on the VPS is overwritten on next push — add to Secrets to persist.

**Never commit secrets** (API tokens, webhooks, VPS hostname, SSH keys, `.env`). If something slips into a commit, rotate the secret — `git push --force` doesn't undo what's already been copied elsewhere.

## DB schema gotchas

- `indicator_snapshots` and `stock_snapshots` have `UNIQUE(indicator/ticker, date)` since migration 0005. Any new write path must include `date` and use upsert semantics.
- `purge_old_data` (Sunday 00:00) keeps only the last 3 years.
- `scripts/dedupe_non_trading_days.py` is a one-shot cleanup against yfinance's trading-day calendar — keep it around for incident recovery, don't delete.
