"""Tests for result caching."""
import json
import pytest
from pathlib import Path


def test_cache_key_is_deterministic(tmp_path):
    from analyzer.cache import CacheKey
    (tmp_path / "results.json").write_text('{"test": 1}')
    k1 = CacheKey.compute(tmp_path, tmp_path / "results.json")
    k2 = CacheKey.compute(tmp_path, tmp_path / "results.json")
    assert k1 == k2
    assert len(k1) == 40  # SHA1 hex


def test_cache_key_changes_when_file_content_changes(tmp_path):
    from analyzer.cache import CacheKey
    p = tmp_path / "results.json"
    p.write_text('{"test": 1}')
    k1 = CacheKey.compute(tmp_path, p)
    p.write_text('{"test": 2}')
    k2 = CacheKey.compute(tmp_path, p)
    assert k1 != k2


def test_save_and_load_cache(tmp_path):
    from analyzer.cache import save_cache, load_cached, CacheKey
    from analyzer.orchestrator import AnalysisResult
    from analyzer.workspace_scanner import WorkspaceProfile
    p = tmp_path / "results.json"
    p.write_text('{"x": 1}')
    key = CacheKey.compute(tmp_path, p)
    result = AnalysisResult(
        framework="jest", failures=[], git={}, logs={}, config={},
        matrix=[], clusters=[], hypotheses=[], report_markdown="# r",
        elapsed_seconds=1.0,
        profile=WorkspaceProfile(mode="API_ONLY", source_roots=[], test_roots=[],
                                  noise_paths=[], openapi_spec=None, has_git=False),
        phase_timings={},
    )
    save_cache(tmp_path, key, result)
    loaded = load_cached(tmp_path, key)
    assert loaded is not None
    assert loaded.framework == "jest"


def test_load_cached_returns_none_when_missing(tmp_path):
    from analyzer.cache import load_cached
    assert load_cached(tmp_path, "nonexistent_key") is None
