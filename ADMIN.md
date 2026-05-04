# Stock Dashboard — Admin Runbook

Operational notes for managing users, API tokens, and the auto-tracked
Taiwan top-100 list. The dashboard runs on a VPS as a `systemd` service
(`stock-dashboard.service`); the SQLite DB lives at
`/opt/stock-dashboard/backend/stock_dashboard.db`.

## Authentication model

- Each `user` (id, name, created_at) has **at most one active API token**.
- Issuing a new token for a user **revokes the previous active token
  immediately**. Any client still holding the old token will get 401.
- Tokens are 39-char `sd_<base64>` strings; only the SHA-256 hash + the
  display prefix (first 6 chars) are stored. **Plaintext is shown once at
  issue time.**
- Token expiry defaults to 365 days; pass `--no-expiry` to issue a
  permanent token. Expired tokens fail auth and need rotation.
- The `watched_stocks` (watchlist) and `price_alerts` (price alerts) tables
  scope by `user_id`. `/api/dashboard`, news, and per-ticker detail
  endpoints are open to any valid token.

## Where the CLI lives

The CLIs run on the VPS where the DB and venv exist:

```bash
ssh root@<VPS_HOST>
cd /opt/stock-dashboard/backend
source .venv/bin/activate                   # uvicorn's venv
```

All commands below assume that working directory + activated venv.

## User management — `manage_users.py`

```bash
# List all users (always shows 'paul' as id=1, the migrated default)
python -m scripts.manage_users list

# Create a new user. Errors with exit 1 if the name already exists.
python -m scripts.manage_users create alice
```

The new user starts with no token and an empty watchlist + alerts.

## Token management — `issue_token.py`

### Issue / rotate a user's token

```bash
# 365-day default expiry
python -m scripts.issue_token issue --user-name alice --label alice-laptop

# Custom expiry
python -m scripts.issue_token issue --user-name alice --label tmp --expires-days 30

# Permanent (no expiry — use sparingly)
python -m scripts.issue_token issue --user-name alice --label permanent --no-expiry
```

If a prior active token exists for that user, it's automatically revoked
in the same transaction. The plaintext token prints to stdout — copy it
once; you cannot recover it later.

If the user doesn't exist the script errors with a pointer:

```
error: user 'bob' not found.
  Run: python -m scripts.manage_users create bob
```

### List tokens

```bash
python -m scripts.issue_token list
```

Output columns: `ID | USER | PREFIX | LABEL | CREATED | LAST_USED | STATUS`.
`STATUS` is one of `active / expired / revoked`. `LAST_USED` updates on
every authenticated request.

### Manual revoke

Used only when you can't reach the user to rotate (compromise, lost
device). Identify the row id from `issue_token list`, then:

```bash
python -m scripts.issue_token revoke 7
```

## Common workflows

### Onboard a new user

```bash
python -m scripts.manage_users create $NAME
python -m scripts.issue_token issue --user-name $NAME --label $NAME-laptop
# share plaintext token via private channel
```

The user pastes the token into the dashboard's TokenGate
(GitHub Pages URL — `easylive1989.github.io/publixia/` or the configured
custom domain); it's stored in `localStorage`
and re-sent as `Authorization: Bearer <token>` on every API request.

### Rotate (expiry approaching, or device replaced)

```bash
python -m scripts.issue_token issue --user-name $NAME --label $NAME-newlaptop
```

The previous active token is revoked the moment this command commits. The
user should clear localStorage on their old device (or log out via the
dashboard's settings) and paste the new token on the new device.

### Audit access

```bash
python -m scripts.manage_users list
python -m scripts.issue_token list
```

Compare `LAST_USED` to a recent timestamp — long gaps suggest a stale
token that can be revoked.

### Emergency: revoke everything for a user

There's no `revoke-all-for-user` shortcut; rotate-and-discard works:

```bash
python -m scripts.issue_token issue --user-name $NAME --label emergency-rotate \
    --expires-days 1
# Don't share the new token; let it expire in 24h.
```

Or revoke directly by id from the `list` output.

## Auto-tracked Taiwan top-100

Taiwan large-caps + popular ETFs are auto-tracked: backend fetchers
prefetch their data even when no user is currently watching them, and
detail endpoints (`/api/stocks/{ticker}/*`) accept any auto-tracked
ticker without requiring it in a user's watchlist.

### Where the list lives

```
stock/dashboard/backend/seeds/auto_tracked_taiwan.txt
```

Newline-delimited tickers in `XXXX.TW` form, with `#` comments. Sectioned
roughly by industry (半導體 / 金融 / 傳產 / ETF…). About 90 tickers in
the initial seed.

### How the list flows into the DB

`init_db()` (called on every service start) reads the file and runs
`INSERT OR IGNORE INTO auto_tracked_stocks` for each ticker. **Removed
entries are NOT deleted** — the table is monotonic. If a stock falls
out of the top 100 next quarter, removing the line in the file just
prevents new DB rows; the old row stays and the stock keeps getting
prefetched. This matches the design choice "只增不減".

### How to add new tickers

1. SSH to the VPS:

   ```bash
   ssh root@<VPS_HOST>
   cd /opt/stock-dashboard
   ```

2. Edit the seed file directly:

   ```bash
   nano backend/seeds/auto_tracked_taiwan.txt
   ```

   Append new lines (any section comment is fine; comments aren't
   parsed). One ticker per line, e.g. `1234.TW    # 公司名`.

3. Restart the service to apply:

   ```bash
   systemctl restart stock-dashboard.service
   journalctl -u stock-dashboard.service -n 5
   # look for: auto_tracked_seeded total=N added=K
   ```

   `added=K` shows how many new rows the seed loader inserted this run.

Alternative: edit the file in the repo, commit + push, the deploy
workflow rsyncs the new file and restarts the service automatically.
This is cleaner since the seed file is version-controlled.

### How to remove a ticker

The DB is monotonic: there's no "remove" workflow. If a stock should
genuinely never be auto-fetched again (e.g. delisted, causing fetcher
errors that flood the logs):

```bash
sqlite3 /opt/stock-dashboard/backend/stock_dashboard.db
sqlite> DELETE FROM auto_tracked_stocks WHERE ticker = '1234.TW';
```

Also remove the line from the seed file so future restarts don't
re-add it. (If you only delete from the DB but leave it in the seed,
the next restart re-inserts.)

### Audit

```bash
# Count + sample
sqlite3 /opt/stock-dashboard/backend/stock_dashboard.db \
  "SELECT COUNT(*), MIN(added_at), MAX(added_at) FROM auto_tracked_stocks"

# Compare seed file vs DB
sqlite3 /opt/stock-dashboard/backend/stock_dashboard.db \
  "SELECT ticker FROM auto_tracked_stocks ORDER BY ticker" > /tmp/db_tickers
grep -E '^[0-9]' backend/seeds/auto_tracked_taiwan.txt | awk '{print $1}' | sort > /tmp/seed_tickers
diff /tmp/db_tickers /tmp/seed_tickers
```

Diff output: lines only in `db_tickers` are stocks that were seeded
historically and later removed from the file — the monotonic policy
keeping them. Lines only in `seed_tickers` shouldn't normally appear
unless the service hasn't restarted since the last edit.

### Detail endpoint behavior

For `/api/stocks/{ticker}/{history,chip,valuation,revenue,financial,
dividend}`:

- Ticker in user's `/api/stocks` watchlist → 200
- Ticker in `auto_tracked_stocks` → 200
- Otherwise → **404** with detail "Ticker not in your watchlist and
  not in the auto-tracked list. Add it via POST /api/stocks first."

This is enforced by `_gate_or_404()` in `api/routes/stocks.py`.

## Database notes

The schema is managed by the migration runner (`db/runner.py`). Migrations
live in `backend/db/migrations/`; they apply on `init_db()` startup, which
runs whenever the `systemd` service restarts.

The user concept landed in migration `0003_users.sql`:

- New `users` table seeded with `paul` (id=1)
- `api_tokens` gets `user_id` FK + partial UNIQUE index
  `(user_id) WHERE revoked_at IS NULL` to enforce 1 active token per user
- `price_alerts` gets `user_id` FK
- `watched_stocks` is rebuilt to use `UNIQUE(user_id, ticker)` so two
  users can independently watch the same ticker
- All existing rows are backfilled to `user_id=1`

The auto-track table landed in migration `0004_auto_tracked.sql`:

- New `auto_tracked_stocks` table (ticker PK, source, added_at)
- Populated from `seeds/auto_tracked_taiwan.txt` on every `init_db()`
  via `INSERT OR IGNORE` (idempotent + monotonic)

Direct DB inspection is fine for auditing:

```bash
sqlite3 /opt/stock-dashboard/backend/stock_dashboard.db
sqlite> SELECT u.name, COUNT(w.id) AS tickers, COUNT(a.id) AS alerts
   ...> FROM users u
   ...> LEFT JOIN watched_stocks w ON w.user_id = u.id
   ...> LEFT JOIN price_alerts a ON a.user_id = u.id
   ...> GROUP BY u.id;
```

## Frontend coordination

The frontend is unaware of the user concept — it just sends the token in
the Authorization header. Backend resolves `token → user_id` per request.
On 401 (expired/revoked), `apiFetch` clears `localStorage` and the
`TokenGate` reappears, prompting the user to paste a fresh token.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 Token user not found` after rotation | DB inconsistency (orphaned api_tokens row) | Inspect `SELECT * FROM api_tokens WHERE user_id NOT IN (SELECT id FROM users)`; if any, revoke or delete |
| `IntegrityError: UNIQUE constraint failed: api_tokens.user_id` on issue | Active row exists but `revoke_token` didn't update | Re-run `issue_token issue` (the script revokes-then-inserts in one transaction); if persistent, manually `UPDATE api_tokens SET revoked_at = datetime('now') WHERE user_id = ? AND revoked_at IS NULL` |
| User reports working token suddenly returns 401 | Someone else rotated (`issue_token issue` for the same user) | List tokens to see which row is now active; reissue if intended, or revoke the unintended one |
| Discord ops alert: `Stock Dashboard auth burst` | 5+ 401s from one IP in 5 min | Check logs (`journalctl -u stock-dashboard.service`) for the IP / token prefix; could be a stale token on a polling client, or scanning attempt |
| Detail endpoint returns 404 for a ticker the user expected to view | Not in user's watchlist and not in auto-tracked seed | User adds via dashboard "+ 新增" or `POST /api/stocks`; or admin appends to `seeds/auto_tracked_taiwan.txt` and restarts |
| Logs flooded with `yfinance: $XXXX.TW: possibly delisted` for an auto-tracked ticker | Seed contains a delisted/never-existed symbol | `DELETE FROM auto_tracked_stocks WHERE ticker = ?` and remove from seed file |

## Service control

```bash
systemctl status  stock-dashboard.service
systemctl restart stock-dashboard.service       # also re-runs migrations
journalctl -u     stock-dashboard.service -f    # tail logs
```

CI deploy via `.github/workflows/deploy-stock-dashboard-backend.yml` runs
the rsync + restart on every push that touches `stock/dashboard/backend/**`.
