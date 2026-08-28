"""Test runner script for tgbot project."""
import sys
sys.path.insert(0, 'D:/tgbot')

import pytest

if __name__ == "__main__":
    # Run all non-integration tests first
    result = pytest.main([
        '-v',
        '--tb=short',
        'tests/test_domain.py',
        'tests/test_logger.py',
        'tests/test_export.py',
        'tests/test_navigation_export.py',
    ])
    print(f"\n{'='*60}")
    print(f"Tests completed with exit code: {result}")
    print(f"{'='*60}")
