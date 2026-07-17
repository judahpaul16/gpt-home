"""Shared test setup.

src.tools.alarm imports langchain at module load, which is not installed in the
test environment; we stub it so the module's pure time-parsing logic can be
loaded. Leaf modules behind a heavy package __init__ are loaded from their file
path via the load_source fixture rather than stubbing first-party code.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

for _name in ("langchain_core", "langchain_core.tools"):
    sys.modules.setdefault(_name, MagicMock())


@pytest.fixture
def load_source():
    """Load a single source file as an isolated module, skipping package __init__."""

    def _load(name, relpath):
        spec = importlib.util.spec_from_file_location(name, SRC / relpath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    return _load
