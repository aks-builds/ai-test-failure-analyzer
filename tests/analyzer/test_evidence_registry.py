"""Tests for EvidenceCollector ABC and EvidenceRegistry."""
from pathlib import Path
import pytest
from analyzer.evidence.collector import EvidenceCollector
from analyzer.evidence.registry import EvidenceRegistry
from analyzer.evidence.bundle import EvidenceBundle


class _AlwaysAvailableCollector(EvidenceCollector):
    name = "always"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace, profile):
        return True

    @classmethod
    def collect(cls, workspace, profile):
        return EvidenceBundle(
            collector_name="always", tier="tier1", available=True,
            summary={"ok": True}, legacy={"available": True}
        )


class _NeverAvailableCollector(EvidenceCollector):
    name = "never"
    tier = "tier2"

    @classmethod
    def is_available(cls, workspace, profile):
        return False

    @classmethod
    def collect(cls, workspace, profile):
        raise AssertionError("should never be called")


class _FailingCollector(EvidenceCollector):
    name = "failing"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace, profile):
        return True

    @classmethod
    def collect(cls, workspace, profile):
        raise RuntimeError("boom")


def _fresh_registry():
    """Return a registry with no registered collectors."""
    r = EvidenceRegistry()
    r._collectors = []
    return r


def test_registry_collects_available(tmp_path):
    r = _fresh_registry()
    r.register(_AlwaysAvailableCollector)
    results = r.collect_all(tmp_path, profile=None, timeout=10)
    assert "always" in results
    assert results["always"].available is True


def test_registry_skips_unavailable(tmp_path):
    r = _fresh_registry()
    r.register(_NeverAvailableCollector)
    results = r.collect_all(tmp_path, profile=None, timeout=10)
    assert "never" in results
    assert results["never"].available is False


def test_registry_handles_collector_exception(tmp_path):
    r = _fresh_registry()
    r.register(_FailingCollector)
    # should not raise — returns empty bundle
    results = r.collect_all(tmp_path, profile=None, timeout=10)
    assert "failing" in results
    assert results["failing"].available is False


def test_collector_abstract_cannot_be_instantiated():
    with pytest.raises(TypeError):
        EvidenceCollector()


def test_git_collector_wraps_legacy_output(tmp_path):
    """GitCollector must return an EvidenceBundle whose .legacy matches
    the exact shape scan_git_history() returns."""
    from analyzer.evidence.collectors.git_collector import GitCollector
    # tmp_path has no .git — collector should be unavailable
    assert GitCollector.is_available(tmp_path, profile=None) is False
    bundle = GitCollector.collect(tmp_path, profile=None)
    assert bundle.available is False
    assert "available" in bundle.legacy


def test_git_collector_available_in_real_repo():
    """Collector is available when .git/ exists (this test runs inside the repo)."""
    from pathlib import Path
    from analyzer.evidence.collectors.git_collector import GitCollector
    repo_root = Path(__file__).parent.parent.parent  # ai-test-failure-analyzer/
    if not (repo_root / ".git").exists():
        pytest.skip("not inside a git repo")
    assert GitCollector.is_available(repo_root, profile=None) is True
