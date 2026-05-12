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

## Strategy permissions & per-user Discord webhooks

The Futures Strategy Engine (`docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md`) is gated by two new per-user fields on the `users` table:

- `can_use_strategy` — boolean. When `0`, the user gets `403` from any
  `/api/strategies/*` endpoint (introduced in P4) and the frontend hides
  the strategy section. Default `0` for every user including `paul`.
- `discord_webhook_url` — nullable text. Per-user webhook for strategy
  notifications. Stored plaintext (same model as the project's `.env`).
  Without one set, the user cannot enable real-time notifications on a
  strategy.

Both are managed exclusively through the admin CLI's per-user submenu.

### Workflows

- **Grant strategy access**: `List users → pick user → Toggle strategy
  permission`. Toggling is idempotent — choosing the action a second
  time revokes.
- **Set per-user webhook**: `List users → pick user → Set Discord
  webhook URL`. The CLI validates the URL pattern
  `https://(discord|discordapp).com/api/webhooks/<id>/<token>` and
  rejects anything else.
- **Rotate webhook**: just call `Set Discord webhook URL` again — it
  overwrites the previous URL.
- **Clear webhook**: `Clear Discord webhook URL`. Asks for confirmation
  because strategies that depend on it will then silently fail to send
  notifications. (In a later phase we will additionally offer to
  auto-disable the user's notify-enabled strategies in the same flow.)

### Audit

The list view shows two new columns, `STRATEGY` (✓/✗) and `WEBHOOK`
(masked URL or `—`). The webhook display elides the secret token
segment so the table can be safely shared/screenshotted.

For a deeper inspection (or to dump every user's raw URL), query the DB
directly:

```bash
sqlite3 /opt/stock-dashboard/backend/stock_dashboard.db \
  "SELECT id, name, can_use_strategy, discord_webhook_url FROM users"
```

## Operating the Futures Strategy Engine

Once a user has `can_use_strategy=1` and a webhook set, they manage their strategies via the `/strategies` page. Operators usually only get involved when something breaks. This section covers the troubleshooting workflows.

### Reading what the engine just did

Each strategy has a signal history (the `strategy_signals` table; UI renders it as 訊號歷史). The full event sequence for a single closed trade is:

1. `ENTRY_SIGNAL` — the engine decided "fire" on bar T (close-of-day). The Discord embed went out at this point.
2. `ENTRY_FILLED` — bar T+1 opened; entry_fill_price recorded. No embed; this is bookkeeping.
3. `EXIT_SIGNAL` — stop-loss / take-profit / TIMEOUT triggered on bar E. Discord embed at this point with reason + estimated PnL.
4. `EXIT_FILLED` — bar E+1 opened; final pnl_amount recorded.

`MANUAL_RESET` shows up only when the user clicked "強制平倉" on the edit page — it's recorded as the `exit_reason` on a synthesised `EXIT_FILLED` row using the latest available bar's close as the assumed fill price. State returns to `idle`. The Discord embed posts.

`RUNTIME_ERROR` shows up when `evaluate_one` raises (e.g. a DSL references a field the bar dict doesn't have). The strategy is auto-disabled (`notify_enabled=0`); the user must edit + re-enable after fixing the cause.

### When a user reports "no signal showed up"

Check, in order:

1. **Was the strategy enabled the day the user expected it to fire?** `SELECT id, name, notify_enabled, last_error FROM strategies WHERE user_id=...`. If `notify_enabled=0` and `last_error` is populated, a runtime error already auto-disabled it.

2. **Did the contract's fetcher run that day?** `SELECT MAX(date) FROM futures_daily WHERE symbol='TX'` (or MTX / TMF). If the latest date isn't the latest trading day, the fetcher failed — check `journalctl -u stock-dashboard.service` for FinMind errors.

3. **Did the engine evaluate the strategy?** Look for log lines: `strategy_notify_signal strategy_id=...` (a signal fired) or `strategy_notify_skip_no_webhook ...` (the user has no webhook).

4. **Does the strategy actually fire on the bar that just landed?** The fastest way is to run a backtest from the user's UI for the range that includes the target date — if the backtest shows no trade on that date, the strategy's logic just didn't trigger; not a bug.

### When a user reports "I'm getting too many false signals"

This is a strategy-design issue, not an ops issue. The user can:

- Tighten the entry conditions in the UI.
- Raise the take-profit % or lower the stop-loss % to reduce whipsawing.
- Add a `streak_above`/`streak_below` requirement (N-day persistence).

Operators don't usually intervene; just confirm the engine is working as designed.

### force_close vs reset

- **force_close** (UI: 強制平倉, only available when state ∈ {open, pending_exit}): use when the user wants to "close the trade now" but keep the strategy's history intact. Writes one `EXIT_FILLED` row with `exit_reason='MANUAL_RESET'` using the latest bar's close as the assumed fill price. State returns to `idle`. The Discord embed posts.

- **reset** (UI: 重置, always available): nuclear option. Deletes the strategy's entire `strategy_signals` history, clears all state machine columns + `last_error`, returns state to `idle`. No Discord embed. Use when the strategy got into a wedged state during development or after a runtime error and the user wants a clean slate.

If a user can't decide which to use: force_close preserves the trade record; reset doesn't. Default to reset for runtime-error recovery, force_close for "I just want out of this trade."

### Common runtime errors and what they mean

The engine catches every `evaluate_one` exception and stores a 1000-char-truncated message in `strategies.last_error` + writes a `RUNTIME_ERROR` signal row. The user sees both on their edit page.

| Error pattern                                  | Likely cause                              |
|------------------------------------------------|-------------------------------------------|
| `KeyError: 'close'`                            | A fetcher persisted a malformed bar (rare); inspect futures_daily for the date in `last_error_at`. |
| `pydantic.ValidationError`                     | DSL became invalid after a schema change. The strategy was enabled before P6's enable-time check landed; just re-edit + save. |
| `ZeroDivisionError` (RSI / change_pct)         | Bar's close was 0 (delisted symbol). Should never happen for TX/MTX/TMF — investigate fetcher. |
| `RuntimeError: FinMind ...` in fetcher logs    | Not a strategy error; FinMind down. Strategy will just not evaluate today; tomorrow's fetcher recovers. |

### Manually re-running a strategy for a day

If a fetcher backfills a missed day after the engine ran, the user's strategy doesn't auto-replay. To force re-evaluation manually on the VPS:

```bash
ssh root@$VPS_HOST
python3 -c "
import sys; sys.path.insert(0, '/opt/stock-dashboard/backend')
from services.strategy_engine import on_futures_data_written
on_futures_data_written('TX', '2026-04-15')
"
```

This iterates every notify-enabled strategy on TX and advances each by one bar against the 2026-04-15 row. **Use sparingly** — it doesn't de-dupe against signals already written for that date, so running it twice in a day will double-write.

### Cleaning up after a failed deploy

If `init_db()` fails mid-migration on deploy and `systemctl restart` loops, the DB might be in a partial state. The `db/runner.py` migrations are forward-only and idempotent, so re-running the deploy usually fixes it. If it doesn't, restore the DB from the previous night's backup (the cleanup job at `0 0 * * 0` is the standard backup trigger) and replay any user actions from the journal.

### Where the engine logs

```bash
journalctl -u stock-dashboard.service -f | grep strategy_
```

Useful greps:
- `strategy_notify_signal` — every Discord-bound signal
- `strategy_notify_skip_no_webhook` — user without webhook
- `strategy_notify_discord_failed` — webhook 5xx / unreachable
- `strategy_evaluate_failed` — full traceback before auto-disable
- `strategy_engine_no_bar` — fetcher hadn't run when engine fired

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
