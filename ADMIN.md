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

## User & token management — `admin/` CLI

User and token administration is done through the standalone interactive
CLI in `admin/` (see [`admin/README.md`](admin/README.md) for setup).

```bash
# One-time venv setup
cd admin && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..

# Run interactively
admin/.venv/bin/python -m admin                                # default DB
DB_PATH=/path/to/stock_dashboard.db admin/.venv/bin/python -m admin
```

The interactive flow covers:

- **List users** — table view of all users + their active token status
  (`active` / `expired` / `none`). Drill into a user to refresh or
  revoke their token.
- **Create user** — prompts for a name; optionally issues an initial
  token in the same flow.
- **Refresh token** — picks a user, prompts for label and expiry
  (365d / 30d / never / custom), revokes the existing active token,
  and prints the new plaintext **once** (copy it immediately — there
  is no recovery).

### Where to run it

The CLI talks to a **local** SQLite file and is fully decoupled from the
backend. Two patterns:

1. **On the VPS** (simplest, no DB copying):

   ```bash
   ssh root@<VPS_HOST>
   cd /opt/stock-dashboard/admin
   .venv/bin/python -m admin
   ```

   The default `DB_PATH` resolution (`<repo>/backend/stock_dashboard.db`)
   matches the deployed layout.

2. **On your laptop** against a copy of the VPS DB — useful for audit.
   Note that any writes (create user, refresh token) only land in the
   local copy unless you `scp` it back and restart the service.

### Common workflows

**Onboard a new user** — choose `Create user`, enter name, accept the
"issue token now" prompt, copy the plaintext, share via a private
channel. The user pastes it into the dashboard's TokenGate
(`https://stock.paul-learning.dev/`).

**Rotate** (expiry approaching or device replaced) — choose
`Refresh token`, pick the user, set label/expiry. The previous active
token is revoked the moment the new one is issued.

**Audit** — `List users` shows token status and expiry at a glance.
For deeper inspection (last-used timestamps, revoked rows) read the
`api_tokens` table directly via `sqlite3`.

**Emergency revoke without reissue** — pick the user from the list,
choose `Revoke active token`. They will get 401 on the next request.

## Detail endpoint behavior

For `/api/stocks/{ticker}/{history,chip,valuation,revenue,financial,
dividend}`:

- Ticker in user's `/api/stocks` watchlist → 200
- Otherwise → **404** with detail "Ticker not in your watchlist. Add it
  via POST /api/stocks first."

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
| `IntegrityError: UNIQUE constraint failed: api_tokens.user_id` on issue | Active row exists but the rotate-revoke step didn't update | Re-run `Refresh token` in the admin CLI (revokes-then-inserts in one transaction); if persistent, manually `UPDATE api_tokens SET revoked_at = datetime('now') WHERE user_id = ? AND revoked_at IS NULL` |
| User reports working token suddenly returns 401 | Someone else rotated (`Refresh token` for the same user) | Inspect `api_tokens` to see which row is now active; reissue if intended, or revoke the unintended one |
| Discord ops alert: `Stock Dashboard auth burst` | 5+ 401s from one IP in 5 min | Check logs (`journalctl -u stock-dashboard.service`) for the IP / token prefix; could be a stale token on a polling client, or scanning attempt |
| Detail endpoint returns 404 for a ticker the user expected to view | Not in user's watchlist | User adds via dashboard "+ 新增" or `POST /api/stocks` |

## Service control

```bash
systemctl status  stock-dashboard.service
systemctl restart stock-dashboard.service       # also re-runs migrations
journalctl -u     stock-dashboard.service -f    # tail logs
```

CI deploy via `.github/workflows/deploy-stock-dashboard-backend.yml` runs
the rsync + restart on every push that touches `stock/dashboard/backend/**`.
