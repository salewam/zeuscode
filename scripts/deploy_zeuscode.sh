#!/usr/bin/env bash
# One-shot deploy local ultra-mode-mvp → /opt/zeuscode on production.
# Usage: ZEUS_HOST=199.189.253.168 ZEUS_PASS='…' ./scripts/deploy_zeuscode.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${ZEUS_HOST:?set ZEUS_HOST}"
PASS="${ZEUS_PASS:?set ZEUS_PASS}"
RSYNC_RSH="sshpass -p ${PASS} ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no"
export RSYNC_RSH

echo "→ rsync to root@${HOST}:/opt/zeuscode"
rsync -az --delete \
  --exclude ".venv/" \
  --exclude ".env" \
  --exclude "data/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".git/" \
  --exclude "node_modules/" \
  --exclude ".DS_Store" \
  "${ROOT}/" "root@${HOST}:/opt/zeuscode/"

echo "→ restart zeuscode"
sshpass -p "${PASS}" ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no \
  "root@${HOST}" 'systemctl restart zeuscode; sleep 2; systemctl is-active zeuscode; curl -sS http://127.0.0.1:8080/health; echo'

echo "OK"
