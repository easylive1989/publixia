#!/usr/bin/env bash
# Deploys stock dashboard backend to VPS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"   # repo root

if [ -z "$VPS_HOST" ]; then
  echo "Error: VPS_HOST 環境變數未設定（請在 ~/.zshrc 中 export VPS_HOST=...）" >&2
  exit 1
fi
VPS=root@$VPS_HOST
REMOTE=/opt/stock-dashboard

echo "==> Syncing code to VPS..."
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='stock_dashboard.db' \
  backend/ $VPS:$REMOTE/backend/

echo "==> Syncing service file..."
rsync -av stock-dashboard.service $VPS:$REMOTE/

echo "==> Installing dependencies on VPS..."
ssh $VPS "
  cd $REMOTE/backend
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
"

echo "==> Installing systemd service..."
ssh $VPS "
  cp $REMOTE/stock-dashboard.service /etc/systemd/system/stock-dashboard.service
  systemctl daemon-reload
  systemctl enable stock-dashboard
  systemctl restart stock-dashboard
  systemctl status stock-dashboard --no-pager
"

echo "==> Done. API live at https://api.paul-learning.dev"
