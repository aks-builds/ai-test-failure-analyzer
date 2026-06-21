"""Tests for DepDiffCollector."""
import json
import pytest
from pathlib import Path


def test_dep_diff_unavailable_without_git(tmp_path):
    from analyzer.evidence.collectors.dep_diff_collector import DepDiffCollector
    (tmp_path / "package.json").write_text('{"dependencies": {}}')
    assert DepDiffCollector.is_available(tmp_path, profile=None) is False


def test_dep_diff_unavailable_without_manifest(tmp_path):
    from analyzer.evidence.collectors.dep_diff_collector import DepDiffCollector
    (tmp_path / ".git").mkdir()
    assert DepDiffCollector.is_available(tmp_path, profile=None) is False


def test_dep_diff_available_with_git_and_manifest(tmp_path):
    from analyzer.evidence.collectors.dep_diff_collector import DepDiffCollector
    (tmp_path / ".git").mkdir()
    (tmp_path / "package.json").write_text('{"dependencies": {}}')
    assert DepDiffCollector.is_available(tmp_path, profile=None) is True


def test_dep_diff_collect_returns_bundle_on_no_git(tmp_path):
    """collect() must return empty bundle (not raise) when git fails."""
    from analyzer.evidence.collectors.dep_diff_collector import DepDiffCollector
    bundle = DepDiffCollector.collect(tmp_path, profile=None)
    assert bundle.available is False
    assert bundle.nodes == []


def test_dep_diff_parse_package_json_diff():
    """_parse_manifest_diff correctly identifies added/removed packages."""
    from analyzer.evidence.collectors.dep_diff_collector import _parse_manifest_diff
    old = json.dumps({"dependencies": {"express": "4.18.0", "axios": "1.4.0"}})
    new = json.dumps({"dependencies": {"express": "4.19.0", "lodash": "4.17.21"}})
    changes = _parse_manifest_diff("package.json", old, new)
    names = {c["package"] for c in changes}
    assert "express" in names  # bumped
    assert "axios" in names   # removed
    assert "lodash" in names  # added
