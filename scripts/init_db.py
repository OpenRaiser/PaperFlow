#!/usr/bin/env python3
"""Initialize local runtime directories and the SQLite database."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def ensure_runtime_dirs() -> None:
    for relative in (
        "data",
        "data/db_backups",
        "data/embeddings_cache",
        "models",
    ):
        (PROJECT_ROOT / relative).mkdir(parents=True, exist_ok=True)

    for relative in ("data/.gitkeep", "models/.gitkeep"):
        path = PROJECT_ROOT / relative
        path.touch(exist_ok=True)


def main() -> int:
    ensure_runtime_dirs()

    db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
    db_ops.init_db()

    print(f"[OK] Runtime directories ready: {PROJECT_ROOT}")
    print(f"[OK] Database ready: {PROJECT_ROOT / 'data' / 'scitaste.db'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

