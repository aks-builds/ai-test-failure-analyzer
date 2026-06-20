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
