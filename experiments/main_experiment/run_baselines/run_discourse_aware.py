#!/usr/bin/env python3
"""CLI wrapper for the Discourse-Aware main-experiment baseline."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.baselines.discourse_aware.runner import main


if __name__ == "__main__":
    main()
