# This file auto-generated to enable Python imports from the master-coordinator directory
# Re-export everything from agents/master-coordinator/main.py

import sys
import importlib.util
from pathlib import Path

# Load the actual module from the hyphenated directory
master_coordinator_path = Path(__file__).parent.parent / "master-coordinator" / "main.py"
if master_coordinator_path.exists():
    spec = importlib.util.spec_from_file_location("master_coordinator_main", master_coordinator_path)
    _module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_module)

    # Re-export all public symbols
    for attr in dir(_module):
        if not attr.startswith('_'):
            globals()[attr] = getattr(_module, attr)

    __all__ = [attr for attr in dir(_module) if not attr.startswith('_')]
