#!/usr/bin/env python3
"""Compatibility wrapper for the BM25 Natural-Language User Profile baseline."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.baselines.scinup_strict.runner import main


if __name__ == "__main__":
    main()
