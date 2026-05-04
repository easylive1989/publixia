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
