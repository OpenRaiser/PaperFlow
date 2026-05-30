"""Download the published PaperFlow-Bench dataset from Hugging Face.

After running this script, ``data/PaperFlow-Bench/`` will contain the same
files that ``prepare_hf_benchmark_package.py`` originally produced, ready for
use with ``experiments/benchmark/evaluate_benchmark_predictions.py`` and
``experiments/benchmark/make_benchmark_submission.py``.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO = "OpenRaiser/PaperFlow"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "PaperFlow-Bench"


def _snapshot(repo_id: str, revision: str | None) -> Path:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - dependency check
        raise SystemExit(
            "huggingface_hub is required. Install with `pip install huggingface_hub`."
        ) from exc

    return Path(
        snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            revision=revision,
            allow_patterns=[
                "data/*.jsonl",
                "reference_outputs/*.jsonl",
                "evaluation/*.py",
                "README.md",
                "VERSION",
            ],
        )
    )


def _mirror(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default=DEFAULT_REPO)
    parser.add_argument("--revision", default=None, help="Branch, tag, or commit hash.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"[fetch] downloading {args.repo_id} (revision={args.revision or 'main'})")
    snapshot = _snapshot(args.repo_id, args.revision)
    print(f"[fetch] mirror {snapshot} -> {args.output_dir}")
    _mirror(snapshot, args.output_dir)
    print(f"[fetch] done: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
