# Publixia Admin CLI

Interactive admin tool for the Publixia stock dashboard. Talks to the
SQLite DB directly — no backend code shared.

## Setup

```bash
cd admin
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```bash
# From repo root
admin/.venv/bin/python -m admin
```

The DB path is read from the `DB_PATH` environment variable. If unset,
defaults to `<repo>/backend/stock_dashboard.db`.

```bash
DB_PATH=/path/to/stock_dashboard.db admin/.venv/bin/python -m admin
```

## Features

- **List users** — table view of all users joined with their active token
  status (`active` / `expired` / `none`). Pick a user to drill into actions.
- **Create user** — prompts for a name, then optionally issues an initial
  token in the same flow.
- **Refresh token** — picks a user, prompts for label and expiry
  (365d / 30d / never / custom), then revokes the existing active token
  and issues a new one. The plaintext token is shown **once** —
  copy it immediately.
- **Manage scheduler** — table view of every scheduled job with its
  cron expression, enabled flag, last run time, and last status. Pick a
  job to edit the cron expression (5-field POSIX, interpreted in
  `Asia/Taipei`) or toggle it on / off. Defaults are seeded by the
  backend from `backend/jobs/registry.py` the first time it boots —
  admin edits override those defaults and are never rewritten.
- **Restart backend service** — runs `systemctl restart stock-dashboard`
  so scheduler edits take effect. Run as root (or via a `sudo` shell)
  on the VPS — does nothing on machines without that systemd unit.
- **Toggle strategy permission** — flips `users.can_use_strategy` for the
  selected user. Hidden gate for the Futures Strategy Engine; off by
  default.
- **Set Discord webhook URL** — stores a per-user webhook for strategy
  notifications. Validates `https://(discord|discordapp).com/api/webhooks/<id>/<token>`
  before persisting.
- **Clear Discord webhook URL** — sets the column back to NULL. Strategies
  that need it to send notifications will then silently skip until a new
  URL is configured.

## Working against the VPS database

The tool only knows how to read a local SQLite file. To manage VPS users
from your laptop, copy the DB down first:

```bash
scp root@$VPS_HOST:/opt/stock-dashboard/backend/stock_dashboard.db /tmp/sd.db
DB_PATH=/tmp/sd.db admin/.venv/bin/python -m admin
scp /tmp/sd.db root@$VPS_HOST:/opt/stock-dashboard/backend/stock_dashboard.db
systemctl restart stock-dashboard  # via SSH
```

For one-off operations it is usually simpler to SSH and run the tool
directly on the VPS.
