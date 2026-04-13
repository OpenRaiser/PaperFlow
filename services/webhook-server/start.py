#!/usr/bin/env python3
"""
Start the Feishu webhook server.

Examples:
    python services/webhook-server/start.py
    python services/webhook-server/start.py --port 9000
    python services/webhook-server/start.py --verify
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass


REQUIRED_ENV_VARS = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_VERIFICATION_TOKEN",
)


def bootstrap_runtime() -> None:
    runtime_bootstrap = importlib.import_module("scripts.runtime_bootstrap")
    runtime_bootstrap.bootstrap_runtime(verbose=True)


def verify_env() -> int:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        print()
        print("Please configure them in .env:")
        print("  FEISHU_APP_ID=cli_xxxxxxxxxxxxx")
        print("  FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx")
        print("  FEISHU_VERIFICATION_TOKEN=xxxxxxxxxxxxxxxx")
        return 1

    print("[OK] All required environment variables are set")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Feishu Webhook Server Starter")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify required environment variables and exit",
    )
    args = parser.parse_args()

    bootstrap_runtime()

    if args.verify:
        return verify_env()

    webhook_server = importlib.import_module("services.webhook-server.scripts.webhook_server")
    scheduler = importlib.import_module("services.webhook-server.scripts.scheduler")

    print(f"[INFO] Starting Feishu webhook server on port {args.port}...")
    print(f"[INFO] Event endpoint: http://127.0.0.1:{args.port}/")
    print(f"[INFO] Health check: http://127.0.0.1:{args.port}/health")
    print(f"[INFO] Automatic schedule: {scheduler.describe_schedule()}")
    print("[INFO] Press Ctrl+C to stop")

    webhook_server.run_server(args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
