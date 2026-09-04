"""Test runner script for TreasuryBot."""
import sys
from pathlib import Path

import pytest

if __name__ == "__main__":
    root_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(root_dir))

    result = pytest.main([
        "-v",
        "--tb=short",
        str(root_dir / "tests"),
    ])
    sys.exit(int(result))

