"""Shared pytest configuration and fixtures."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# Root of the repository (two levels up from tests/)
_REPO_ROOT = Path(__file__).parent.parent
_ATFA_CACHE = _REPO_ROOT / ".atfa" / "cache"


@pytest.fixture(autouse=True)
def _clean_atfa_cache():
    """Remove any .atfa/cache entries written during each test.

    Tests that run analyze() against the real REPO workspace share the same
    cache directory.  Clearing it before and after each test prevents cache
    hits from one test masking a real analysis failure in a later test.
    """
    # Clear before test so stale cache files don't affect this run
    if _ATFA_CACHE.exists():
        shutil.rmtree(_ATFA_CACHE, ignore_errors=True)
    yield
    # Clear after test so cache artifacts don't linger in the working tree
    if _ATFA_CACHE.exists():
        shutil.rmtree(_ATFA_CACHE, ignore_errors=True)
