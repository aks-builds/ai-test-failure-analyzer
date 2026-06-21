"""Tests for CIContextCollector."""
import os
import pytest


def test_ci_context_unavailable_locally(monkeypatch):
    """Not available when no CI env vars are set."""
    from analyzer.evidence.collectors.ci_context_collector import CIContextCollector
    from pathlib import Path
    for var in ("GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI", "JENKINS_URL"):
        monkeypatch.delenv(var, raising=False)
    assert CIContextCollector.is_available(Path("."), profile=None) is False


def test_ci_context_available_on_github_actions(monkeypatch, tmp_path):
    from analyzer.evidence.collectors.ci_context_collector import CIContextCollector
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    assert CIContextCollector.is_available(tmp_path, profile=None) is True


def test_ci_context_collect_returns_bundle(monkeypatch, tmp_path):
    from analyzer.evidence.collectors.ci_context_collector import CIContextCollector
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "def456")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/42/merge")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    bundle = CIContextCollector.collect(tmp_path, profile=None)
    assert bundle.collector_name == "ci_context"
    assert "provider" in bundle.summary


def test_ci_context_collect_never_raises(monkeypatch, tmp_path):
    from analyzer.evidence.collectors.ci_context_collector import CIContextCollector
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    # Force an error by making GITHUB_TOKEN invalid — should not raise
    monkeypatch.setenv("GITHUB_TOKEN", "invalid-token-that-will-fail")
    bundle = CIContextCollector.collect(tmp_path, profile=None)
    assert bundle is not None
