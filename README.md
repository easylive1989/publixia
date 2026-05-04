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
tests/                   pytest backend test suite (run from repo root)
stock-dashboard.service  systemd unit copied to VPS
deploy.sh                Manual VPS deploy (used outside CI)
.github/workflows/       CI: deploy-backend.yml, deploy-frontend.yml
```

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

The API enforces `Authorization: Bearer <token>` on every endpoint.

```bash
# 1. Make sure the ops Discord webhook is set (Secrets-driven on every deploy):
#    DISCORD_STOCK_WEBHOOK_URL is enough for normal use.

# 2. Create the user (only needed once per person)
ssh root@$VPS_HOST 'cd /opt/stock-dashboard/backend && .venv/bin/python -m scripts.manage_users create <name>'

# 3. Issue the user a token
ssh root@$VPS_HOST 'cd /opt/stock-dashboard/backend && .venv/bin/python -m scripts.issue_token issue --user-name <name> --label <label>'
# → Copy the printed sd_... token (shown only once)

# 4. Paste the token into the dashboard's TokenGate prompt.
```

The token is kept in browser `localStorage`. The 🔓 重新登入 button on the header clears it.

Token CLI:

```bash
python -m scripts.issue_token issue --user-name <name> --label <label>           # 365 days default
python -m scripts.issue_token issue --user-name <name> --label <label> --no-expiry
python -m scripts.issue_token list
python -m scripts.issue_token revoke <id>
```

## Disabled: 券商分點

`/api/stocks/{ticker}/brokers` returns an empty payload (`ok: false`). FinMind's `TaiwanStockTradingDailyReport` dataset went Sponsor-only; the fetcher / table / token are kept for future reactivation but the frontend no longer calls the endpoint.
