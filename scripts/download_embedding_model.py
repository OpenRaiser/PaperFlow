#!/usr/bin/env python3
"""Download a local embedding model snapshot into the repo's ignored models directory."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from huggingface_hub import snapshot_download


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_ID = "Qwen/Qwen3-Embedding-8B"
DEFAULT_DEST = PROJECT_ROOT / "models" / "Qwen3-Embedding-8B"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a local embedding model snapshot.")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help="Hugging Face model id.")
    parser.add_argument(
        "--dest",
        default=str(DEFAULT_DEST),
        help="Local destination directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dest = Path(args.dest).expanduser()
    if not dest.is_absolute():
        dest = (PROJECT_ROOT / dest).resolve()

    dest.parent.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("HF_TOKEN") or None

    print(f"Downloading {args.model_id} -> {dest}")
    snapshot_download(
        repo_id=args.model_id,
        local_dir=str(dest),
        token=token,
    )

    print("")
    print("Done. Add these lines to .env when you want to use the local snapshot:")
    print("EMBEDDING_PROVIDER=local")
    print(f"LOCAL_EMBEDDING_MODEL_PATH={dest}")
    print("LOCAL_EMBEDDING_TRUST_REMOTE_CODE=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
