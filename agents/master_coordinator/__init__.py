# Placeholder for master_coordinator module
# This file enables importing agents.master_coordinator despite the hyphen in the directory name

import sys
import importlib.util
from pathlib import Path

# Load the actual module from the hyphenated directory
master_coordinator_path = Path(__file__).parent.parent / "master-coordinator" / "main.py"
if master_coordinator_path.exists():
    spec = importlib.util.spec_from_file_location("master_coordinator_impl", master_coordinator_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agents.master_coordinator.main"] = module
    spec.loader.exec_module(module)
