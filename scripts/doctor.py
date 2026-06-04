#!/usr/bin/env python3
"""Check whether a local PaperFlow checkout is ready to run."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - handled by dependency check
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_IMPORTS = [
    "requests",
    "dotenv",
    "numpy",
    "feedparser",
    "yaml",
    "fitz",
    "openai",
]
REQUIRED_FEISHU_ENV = [
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_VERIFICATION_TOKEN",
]
REQUIRED_MODEL_ENV = [
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "PAPERFLOW_LLM_MODEL",
]


def status(ok: bool, label: str, detail: str = "") -> None:
    mark = "OK" if ok else "WARN"
    suffix = f" - {detail}" if detail else ""
    print(f"[{mark}] {label}{suffix}")


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_python() -> bool:
    version = sys.version_info
    ok = version >= (3, 10)
    status(ok, "Python version", f"{version.major}.{version.minor}.{version.micro}")
    return ok


def check_imports() -> bool:
    ok = True
    for module in REQUIRED_IMPORTS:
        available = module_available(module)
        status(available, f"import {module}")
        ok = ok and available
    return ok


def check_env_file() -> bool:
    env_path = PROJECT_ROOT / ".env"
    example_path = PROJECT_ROOT / ".env.example"
    status(example_path.exists(), ".env.example")
    status(env_path.exists(), ".env", "copy .env.example to .env before deployment" if not env_path.exists() else "")
    if load_dotenv and env_path.exists():
        load_dotenv(env_path)
    return env_path.exists()


def check_env_group(title: str, names: list[str]) -> bool:
    print(f"\n{title}")
    ok = True
    for name in names:
        present = bool(os.environ.get(name, "").strip())
        status(present, name)
        ok = ok and present
    return ok


def check_paths() -> bool:
    print("\nRuntime paths")
    ok = True
    for relative in ("agents", "skills", "deployments/feishu/webhook-server", "config", "scripts", "paperflow"):
        path = PROJECT_ROOT / relative
        exists = path.exists()
        status(exists, relative)
        ok = ok and exists

    data_dir = PROJECT_ROOT / "data"
    models_dir = PROJECT_ROOT / "models"
    status(data_dir.exists(), "data/", "created by scripts/init_db.py" if not data_dir.exists() else "")
    status(models_dir.exists(), "models/", "created by scripts/init_db.py" if not models_dir.exists() else "")
    return ok


def check_optional_tools() -> None:
    print("\nOptional tools")
    ngrok_path = os.environ.get("NGROK_PATH", "").strip() or shutil.which("ngrok") or shutil.which("ngrok.exe")
    status(bool(ngrok_path), "ngrok", str(ngrok_path or "not found"))
    lark_cli = os.environ.get("FEISHU_CLI_CMD", "").strip() or shutil.which("lark-cli") or shutil.which("lark-cli.cmd")
    status(bool(lark_cli), "lark-cli", str(lark_cli or "not found"))
    rg = shutil.which("rg")
    status(bool(rg), "ripgrep", str(rg or "optional but useful"))


def main() -> int:
    print("PaperFlow doctor")
    print(f"Project root: {PROJECT_ROOT}\n")

    hard_ok = True
    hard_ok = check_python() and hard_ok
    hard_ok = check_imports() and hard_ok
    check_env_file()
    check_paths()
    feishu_ok = check_env_group("Feishu / Lark", REQUIRED_FEISHU_ENV)
    model_ok = check_env_group("Model API", REQUIRED_MODEL_ENV)
    check_optional_tools()

    print("\nSummary")
    if hard_ok and feishu_ok and model_ok:
        status(True, "PaperFlow is ready to run")
        return 0

    status(False, "PaperFlow is not fully configured")
    print("Fill .env and rerun: python scripts/doctor.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
