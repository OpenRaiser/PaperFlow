#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "========================================="
echo "  SciTaste Initialization"
echo "========================================="
echo

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[1/5] Created .env from .env.example"
else
  echo "[1/5] .env already exists"
fi

if [ ! -f data/roles.json ] && [ -f config/roles.example.json ]; then
  cp config/roles.example.json data/roles.json
  echo "[2/5] Created data/roles.json from config/roles.example.json"
else
  echo "[2/5] data/roles.json already exists"
fi

echo "[3/5] Installing dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "[4/5] Initializing runtime folders and database..."
python scripts/init_db.py

echo "[5/5] Verifying required Feishu environment variables..."
python services/webhook-server/start.py --verify

echo
echo "========================================="
echo "  Initialization Complete"
echo "========================================="
echo
echo "Next steps:"
echo "1. Edit .env and fill in your Feishu / ngrok / model config"
echo "2. Start the webhook locally: python services/webhook-server/start-with-ngrok.py"
echo "3. Copy data/feishu_request_url.txt into Feishu Event Subscription"
