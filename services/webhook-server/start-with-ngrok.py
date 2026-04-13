#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Start the local Feishu webhook server and ensure there is an ngrok URL for it.

This script prefers reusing an existing local ngrok agent when available. It
will:
1. start the webhook server if it is not already healthy
2. reuse an existing tunnel to localhost:<port> when possible
3. otherwise create a tunnel via the local ngrok API
4. if no local ngrok agent is running, start one with `ngrok http <port>`

Useful outputs:
    data/ngrok_url.txt
    data/feishu_request_url.txt
    data/ngrok_runtime.log
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import socket
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
NGROK_API_BASE = "http://127.0.0.1:4040/api"
DEFAULT_PORT = 8080
DEFAULT_TUNNEL_NAME = "scitaste-webhook"
REQUIRED_ENV_VARS = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_VERIFICATION_TOKEN",
)

sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass


def verify_required_env() -> None:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        print()
        print("Please configure them in .env before starting the webhook:")
        print("  FEISHU_APP_ID=cli_xxxxxxxxxxxxx")
        print("  FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx")
        print("  FEISHU_VERIFICATION_TOKEN=xxxxxxxxxxxxxxxx")
        raise SystemExit(1)


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 3.0,
) -> dict[str, Any] | None:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def ngrok_api_get(path: str) -> dict[str, Any] | None:
    return http_json("GET", f"{NGROK_API_BASE}{path}")


def ngrok_api_post(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    return http_json("POST", f"{NGROK_API_BASE}{path}", payload=payload)


def ngrok_api_delete(path: str) -> dict[str, Any] | None:
    return http_json("DELETE", f"{NGROK_API_BASE}{path}")


def ngrok_api_online() -> bool:
    return ngrok_api_get("/status") is not None


def get_tunnels() -> list[dict[str, Any]]:
    response = ngrok_api_get("/tunnels")
    if not response:
        return []
    return response.get("tunnels", [])


def tunnel_matches_port(tunnel: dict[str, Any], port: int) -> bool:
    addr = str(tunnel.get("config", {}).get("addr", "")).strip().lower()
    accepted = {
        f"http://localhost:{port}",
        f"http://127.0.0.1:{port}",
        f"localhost:{port}",
        f"127.0.0.1:{port}",
        str(port),
    }
    return addr in accepted


def get_existing_tunnel(port: int) -> dict[str, Any] | None:
    tunnels = get_tunnels()
    https_tunnel = None
    for tunnel in tunnels:
        if not tunnel_matches_port(tunnel, port):
            continue
        if str(tunnel.get("proto")) == "https":
            return tunnel
        if https_tunnel is None:
            https_tunnel = tunnel
    return https_tunnel


def is_webhook_healthy(port: int, timeout: float = 2.0) -> bool:
    url = f"http://127.0.0.1:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("status") == "healthy"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def wait_for_webhook(port: int, timeout_seconds: int = 15) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_webhook_healthy(port):
            return True
        time.sleep(0.5)
    return False


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start_webhook_thread(port: int) -> tuple[threading.Thread, dict[str, str | None]]:
    webhook_server = importlib.import_module("services.webhook-server.scripts.webhook_server")
    startup_state: dict[str, str | None] = {"error": None}

    def target() -> None:
        try:
            webhook_server.run_server(port)
        except Exception as exc:
            startup_state["error"] = repr(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, startup_state


def ensure_ngrok_cli_available() -> str:
    candidate_paths = [
        os.environ.get("NGROK_PATH", "").strip(),
        shutil.which("ngrok"),
        shutil.which("ngrok.exe"),
        str(Path.home() / "AppData" / "Local" / "ngrok" / "ngrok.exe"),
        str(Path.home() / "Downloads" / "ngrok.exe"),
    ]

    for env_var in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        base_dir = os.environ.get(env_var, "").strip()
        if base_dir:
            candidate_paths.append(str(Path(base_dir) / "ngrok" / "ngrok.exe"))

    seen: set[str] = set()
    for candidate in candidate_paths:
        if not candidate:
            continue
        normalized = os.path.normpath(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isfile(normalized):
            return normalized

    print("[ERROR] ngrok is not installed or cannot be found.")
    print("Install it from https://ngrok.com/download and make sure one of these works:")
    print("  1. `ngrok version`")
    print("  2. set NGROK_PATH=C:\\path\\to\\ngrok.exe")
    print("  3. place ngrok.exe in a common install folder such as %LocalAppData%\\ngrok\\")
    print("Then run `ngrok config add-authtoken <token>` once.")
    raise SystemExit(1)


def configure_ngrok_authtoken(ngrok_binary: str) -> None:
    authtoken = os.environ.get("NGROK_AUTHTOKEN", "").strip()
    if not authtoken:
        return

    result = subprocess.run(
        [ngrok_binary, "config", "add-authtoken", authtoken],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        print("[OK] ngrok authtoken refreshed from NGROK_AUTHTOKEN")
    else:
        print("[WARN] Failed to refresh ngrok authtoken from environment")


def start_ngrok_process(port: int) -> tuple[subprocess.Popen[str], Any]:
    ngrok_binary = ensure_ngrok_cli_available()
    configure_ngrok_authtoken(ngrok_binary)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = DATA_DIR / "ngrok_runtime.log"
    log_file = open(log_path, "a", encoding="utf-8")

    process = subprocess.Popen(
        [ngrok_binary, "http", str(port)],
        cwd=str(ROOT_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, log_file


def wait_for_tunnel(port: int, timeout_seconds: int = 20) -> dict[str, Any] | None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        tunnel = get_existing_tunnel(port)
        if tunnel:
            return tunnel
        time.sleep(0.5)
    return None


def create_tunnel_via_api(port: int, tunnel_name: str) -> dict[str, Any] | None:
    payload = {
        "name": tunnel_name,
        "proto": "http",
        "addr": f"http://localhost:{port}",
        "inspect": True,
    }
    return ngrok_api_post("/tunnels", payload)


def delete_tunnel_via_api(tunnel_name: str) -> None:
    encoded_name = urllib.parse.quote(tunnel_name, safe="")
    ngrok_api_delete(f"/tunnels/{encoded_name}")


def write_url_files(public_url: str) -> tuple[Path, Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ngrok_url_path = DATA_DIR / "ngrok_url.txt"
    feishu_url_path = DATA_DIR / "feishu_request_url.txt"
    request_url = public_url.rstrip("/") + "/"

    ngrok_url_path.write_text(public_url.rstrip("/") + "\n", encoding="utf-8")
    feishu_url_path.write_text(request_url + "\n", encoding="utf-8")
    return ngrok_url_path, feishu_url_path


def print_summary(port: int, public_url: str, ngrok_url_path: Path, feishu_url_path: Path) -> None:
    request_url = public_url.rstrip("/") + "/"
    print()
    print("=" * 60)
    print("SciTaste Webhook + ngrok Ready")
    print("=" * 60)
    print(f"Local webhook : http://127.0.0.1:{port}/")
    print(f"Health check   : http://127.0.0.1:{port}/health")
    print(f"ngrok URL      : {public_url}")
    print(f"Request URL    : {request_url}")
    print(f"Saved URL file : {ngrok_url_path}")
    print(f"Saved URL file : {feishu_url_path}")
    print("ngrok dashboard: http://127.0.0.1:4040")
    print()
    print("Feishu setup:")
    print("1. Open Feishu Open Platform -> your app -> Event Subscription")
    print(f"2. Set Request URL to {request_url}")
    print("3. Enable event: Receive Messages v1.0 (im.message.receive_v1)")
    print("4. Save the subscription")
    print()
    print("Press Ctrl+C to stop.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Feishu webhook server with ngrok")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Local webhook port")
    parser.add_argument(
        "--ngrok-timeout",
        type=int,
        default=20,
        help="Seconds to wait for ngrok tunnel to become ready",
    )
    parser.add_argument(
        "--ngrok-only",
        action="store_true",
        help="Do not start webhook server, only ensure the ngrok tunnel exists",
    )
    args = parser.parse_args()

    verify_required_env()

    if not args.ngrok_only:
        if is_webhook_healthy(args.port):
            print(f"[OK] Reusing existing healthy webhook server on port {args.port}")
        else:
            print(f"[INFO] Starting webhook server on port {args.port}...")
            _, startup_state = start_webhook_thread(args.port)
            if not wait_for_webhook(args.port):
                if startup_state.get("error"):
                    print(f"[ERROR] Webhook server failed to start: {startup_state['error']}")
                elif is_port_in_use(args.port):
                    print(
                        f"[ERROR] Port {args.port} is already occupied, "
                        "but /health did not respond as a SciTaste webhook"
                    )
                else:
                    print("[ERROR] Webhook server did not become healthy in time")
                return 1
            print("[OK] Webhook server is healthy")

    started_ngrok_process = None
    ngrok_log_file = None
    created_tunnel_name = None

    existing_tunnel = get_existing_tunnel(args.port)
    if existing_tunnel:
        public_url = str(existing_tunnel.get("public_url", "")).strip()
        print(f"[OK] Reusing existing ngrok tunnel: {public_url}")
    else:
        if ngrok_api_online():
            created_tunnel_name = f"{DEFAULT_TUNNEL_NAME}-{args.port}"
            print("[INFO] Local ngrok agent is already running, creating a tunnel via local API...")
            created_tunnel = create_tunnel_via_api(args.port, created_tunnel_name)
            if not created_tunnel:
                print("[ERROR] Failed to create ngrok tunnel via local API")
                return 1
            public_url = str(created_tunnel.get("public_url", "")).strip()
            print(f"[OK] Created ngrok tunnel: {public_url}")
        else:
            print("[INFO] No local ngrok agent detected, starting ngrok...")
            started_ngrok_process, ngrok_log_file = start_ngrok_process(args.port)
            created_tunnel = wait_for_tunnel(args.port, timeout_seconds=args.ngrok_timeout)
            if not created_tunnel:
                print("[ERROR] ngrok tunnel did not become ready in time")
                print(f"[INFO] Check log: {DATA_DIR / 'ngrok_runtime.log'}")
                if started_ngrok_process.poll() is None:
                    started_ngrok_process.terminate()
                if ngrok_log_file:
                    ngrok_log_file.close()
                return 1
            public_url = str(created_tunnel.get("public_url", "")).strip()
            print(f"[OK] Started ngrok tunnel: {public_url}")

    ngrok_url_path, feishu_url_path = write_url_files(public_url)
    print_summary(args.port, public_url, ngrok_url_path, feishu_url_path)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        print("[INFO] Shutting down...")
    finally:
        if created_tunnel_name:
            delete_tunnel_via_api(created_tunnel_name)
            print(f"[OK] Removed ngrok tunnel {created_tunnel_name}")
        if started_ngrok_process and started_ngrok_process.poll() is None:
            started_ngrok_process.terminate()
            try:
                started_ngrok_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                started_ngrok_process.kill()
            print("[OK] Stopped ngrok process")
        if ngrok_log_file:
            ngrok_log_file.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
