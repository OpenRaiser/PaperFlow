#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "========================================="
echo "  PaperFlow Initialization"
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
pip install -e ".[all]"

echo "[4/5] Initializing runtime folders and database..."
paperflow init

echo "[5/5] Verifying environment..."
paperflow doctor

echo
echo "========================================="
echo "  Initialization Complete"
echo "========================================="
echo
echo "Next steps:"
echo "1. Edit .env to set provider keys (PAPERFLOW_LLM_PROVIDER, OPENAI_API_KEY, ...)"
echo "2. Try the offline demo:    paperflow demo"
echo "3. Run a daily push (dry):  paperflow daily --user-id alice --dry-run"
echo
echo "Optional Feishu deployment:"
echo "  python deployments/feishu/webhook-server/start-with-ngrok.py"
