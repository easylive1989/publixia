---
name: fix-trade-signal
description: >
  Correct a mislabeled, wrong, or missing AI-extracted stock signal in this
  copy-trading tracker's production database. Use this whenever the user says a
  trade/signal/喊單 is wrong or got missed — e.g. "這單標錯了", "這篇沒抓到台積電",
  "把這個 buy 改成 sell", "這根本不是交易訊號別標", "漏抓了長榮的賣出", "國巨應該是賣不是買",
  "幫我修一下這則的訊號", "這個方向反了". Triggers even when they just point at a
  post/episode and say the extracted call is incorrect. The skill asks which signal
  is wrong, locates the post, and edits `extracted_trades` on the VPS so the
  scoreboard/timeline reflect the fix. Do NOT use for changing extraction prompts
  or stock-reference aliases — that's a code change, not a per-post correction.
---

# Fix a trade signal

The app extracts buy/sell calls from each person's posts with an LLM. It
sometimes mislabels (wrong direction, wrong stock) or misses a call. This skill
corrects the **production** data for one post at a time, going through the
project's own `normalize()` + price-tracking code so the fix is indistinguishable
from a real extraction.

Manual fixes are durable: scheduled extraction only touches `pending`/`error`
posts, and stale re-extraction on prompt bumps is disabled — a `done` post you've
corrected stays corrected.

## Before you touch anything

- **Confirm the exact post and the exact change with the user before writing.**
  This mutates live data. Always `show` the current state and read it back.
- **One post at a time.** Each fix is a *full replace* of that post's signals,
  so you must know the complete correct set for the post (keep the calls that
  were already right).
- **Never invent prices/quantities/dates.** Only include `price`/`quantity`/
  `trade_date` if the post actually stated them (and they're usually null).

## Reaching the production DB

The DB is `/opt/stock-dashboard/backend/stock_dashboard.db` on the VPS. The
project code (with `normalize()` and price tracking) is at
`/opt/stock-dashboard/backend` with a venv at `.venv`.

1. Resolve the host: `echo "${VPS_HOST:-}"`. If empty, ask the user for it
   (it's the same host they deploy with via `./deploy.sh`). Use `root@<host>`.
2. Copy this skill's helper to the VPS once per session:
   `scp <skill-dir>/scripts/fix_trade.py root@$VPS_HOST:/tmp/fix_trade.py`
3. Run it with the project venv:
   `ssh root@$VPS_HOST '/opt/stock-dashboard/backend/.venv/bin/python /tmp/fix_trade.py <cmd> ...'`

`ssh`/`scp` may need a permission prompt — that's expected.

## Workflow

### 1. Identify the post
Ask only what you need to pin it down: which person, plus a content snippet,
episode title, or rough time. Then find its id:

```
ssh root@$VPS_HOST '.../.venv/bin/python /tmp/fix_trade.py find "緯創"'
```

If several match, show them and let the user pick the `#id`.

### 2. Show the current signals
```
... fix_trade.py show <post_id>
```
Read the post text + its current `extracted_trades` back to the user and confirm
this is the one, and exactly what's wrong.

### 3. Decide the corrected signal set
Figure out the **complete** desired list for the post (the helper replaces all of
it). Direction is one of `buy | sell | hold | bullish | bearish`. `ticker`/
`market` are filled automatically by `normalize()`, so you only supply
`raw_symbol` + `direction` (use the name the way the post says it — e.g. `國巨`,
`台積電`, `NVDA`). Common cases:

| Problem | Corrected set |
|---|---|
| Direction reversed (買→賣) | same signals, fix the one `direction` |
| Wrong stock extracted | replace that signal's `raw_symbol` |
| Not a trade at all (discussion/ad) | drop that signal (omit it) |
| Whole post wrongly flagged | `[]` (clears all) |
| A call was missed | add a signal for it |
| raw_symbol right but ticker null | usually a stock_reference alias gap — see note |

### 4. Apply (after the user confirms the JSON)
Pass the full corrected list as a JSON array. To avoid shell-escaping pain with
Chinese names and quotes, pipe the JSON to the helper's stdin with `set <id> -`
via a heredoc. Example — fix #1234 to a single 國巨 sell:

```
ssh root@$VPS_HOST '/opt/stock-dashboard/backend/.venv/bin/python /tmp/fix_trade.py set 1234 -' <<'JSON'
[{"raw_symbol":"國巨","direction":"sell"}]
JSON
```

The helper normalizes, replaces the trades, recomputes that post's price
tracking, and prints the new state. Read it back to the user.

### 5. Verify
Confirm via the live API that the fix shows up:
`curl -s https://api.paul-learning.dev/api/people/<person_key>/posts | ...`
(or `/api/scoreboard` if the change affects standings).

## Notes & edge cases

- **ticker stays null after a fix**: the raw_symbol didn't resolve in
  `stock_reference`. That's an alias/roster gap, not a per-post problem — the fix
  itself is fine, but to make it (and future mentions) resolve, add the alias in
  `backend/services/stock_reference_sync.py` `_*_ALIAS_OVERLAY` (a code change +
  deploy), not here.
- **Direction meaning** (for picking the right one): `buy`/`bullish` count as a
  long call, `sell`/`bearish` as a sell call, `hold` is excluded from scoring.
  The scoreboard grades buy-that-rose / sell-that-fell as wins.
- **Re-running everything**: if after a prompt change you *do* want to reprocess
  old posts, that's the manual path mentioned in `extraction_runner.run_extraction`
  (`set_extraction_status(id, 'pending')`), not this skill.
