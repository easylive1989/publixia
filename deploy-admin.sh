#!/usr/bin/env bash
# Deploys admin CLI to VPS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"   # repo root

if [ -z "$VPS_HOST" ]; then
  echo "Error: VPS_HOST 環境變數未設定（請在 ~/.zshrc 中 export VPS_HOST=...）" >&2
  exit 1
fi
VPS=root@$VPS_HOST
REMOTE=/opt/stock-dashboard

echo "==> Syncing admin/ to VPS..."
rsync -av --delete \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  admin/ $VPS:$REMOTE/admin/

echo "==> Installing dependencies on VPS..."
ssh $VPS "
  cd $REMOTE/admin
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
"

echo "==> Done. 在 VPS 上跑："
echo "    ssh $VPS -t 'cd $REMOTE && admin/.venv/bin/python -m admin'"
