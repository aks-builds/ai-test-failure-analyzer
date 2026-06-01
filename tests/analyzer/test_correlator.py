"""Correlator + hypothesis tests."""

from __future__ import annotations

from pathlib import Path

from analyzer.evidence import cluster_failures, correlate, scan_config, scan_git_history, scan_logs
from analyzer.hypothesis import form_hypotheses
from analyzer.parsers import parse

DEMO_RESULTS = Path(__file__).parent / "fixtures" / "playwright_results.json"


def test_correlate_against_demo_data():
    _, failures = parse(DEMO_RESULTS)
    corr = correlate(failures, git=None, logs=None, config=None)
    assert "matrix" in corr
    assert len(corr["matrix"]) == 3  # 3 failing tests in the demo


def test_cluster_groups_404_failures():
    _, failures = parse(DEMO_RESULTS)
    corr = correlate(failures, git=None, logs=None, config=None)
    clusters = cluster_failures(failures, corr["matrix"])
    assert clusters
    # All 3 failures share the same 404 pattern — we expect them to land in one or two clusters
    total_in_clusters = sum(c["size"] for c in clusters)
    assert total_in_clusters == 3


def test_hypotheses_have_confidence_and_remediation():
    _, failures = parse(DEMO_RESULTS)
    corr = correlate(failures, git=None, logs=None, config=None)
    clusters = cluster_failures(failures, corr["matrix"])
    hyps = form_hypotheses(failures, clusters, corr["matrix"], None, None, None)
    assert hyps
    for h in hyps:
        assert 0 <= h.confidence <= 100
        assert h.title
        assert h.summary
        assert h.remediation
        assert h.affected_tests


def test_hypothesis_titles_match_demo_pattern():
    """The demo data has 404s on different endpoints — should be flagged as endpoint rename."""
    _, failures = parse(DEMO_RESULTS)
    corr = correlate(failures, git=None, logs=None, config=None)
    clusters = cluster_failures(failures, corr["matrix"])
    hyps = form_hypotheses(failures, clusters, corr["matrix"], None, None, None)
    titles = " ".join(h.title.lower() for h in hyps)
    # Should mention endpoint, route, stale resource, or rename
    assert any(kw in titles for kw in ("endpoint", "route", "stale", "rename", "restructure", "resource"))
