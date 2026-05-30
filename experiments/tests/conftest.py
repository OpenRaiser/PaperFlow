"""Test path setup for the experiment test suite."""

from __future__ import annotations

import sys
import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS_ROOT = PROJECT_ROOT / "experiments"

for path in (PROJECT_ROOT, EXPERIMENTS_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


_SHARED_FIXTURES_PATH = PROJECT_ROOT / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("_paperflow_shared_test_fixtures", _SHARED_FIXTURES_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Unable to load shared test fixtures from {_SHARED_FIXTURES_PATH}")
_shared_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_shared_fixtures)

test_db_path = _shared_fixtures.test_db_path
sample_profile = _shared_fixtures.sample_profile
sample_paper = _shared_fixtures.sample_paper
sample_papers_batch = _shared_fixtures.sample_papers_batch
