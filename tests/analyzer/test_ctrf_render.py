"""Tests for CTRF render output."""
import json
import pytest


def _make_result(framework="playwright", hypotheses=None):
    """Create a minimal AnalysisResult for testing."""
    import time
    from analyzer.orchestrator import AnalysisResult
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    from analyzer.workspace_scanner import WorkspaceProfile
    f = NormalizedFailure(
        id=make_failure_id(framework, "suite", "test_a", "test.spec.ts"),
        framework=framework, suite="suite", title="test_a",
        file="test.spec.ts", status="failed",
        error_message="Expected 201 but got 404",
    )
    return AnalysisResult(
        framework=framework,
        failures=[f],
        git={"available": False, "commits": [], "summary": {}},
        logs={"available": False, "matches": [], "summary": {}},
        config={"available": False, "files": [], "summary": {}},
        matrix=[],
        clusters=[],
        hypotheses=hypotheses or [],
        report_markdown="# report",
        elapsed_seconds=1.5,
        profile=WorkspaceProfile(
            mode="FULL_SOURCE", source_roots=[], test_roots=[], noise_paths=[],
            openapi_spec=None, has_git=False,
        ),
        phase_timings={},
    )


def test_ctrf_render_produces_valid_json():
    from analyzer.render.ctrf import render_ctrf_report
    result = _make_result()
    output = render_ctrf_report(result)
    parsed = json.loads(output)
    assert "results" in parsed
    assert "tool" in parsed["results"]
    assert "summary" in parsed["results"]
    assert "tests" in parsed["results"]


def test_ctrf_render_summary_counts_match():
    from analyzer.render.ctrf import render_ctrf_report
    result = _make_result()
    parsed = json.loads(render_ctrf_report(result))
    summary = parsed["results"]["summary"]
    assert summary["tests"] == 1
    assert summary["failed"] == 1
    assert summary["passed"] == 0


def test_ctrf_render_test_has_ai_field_when_hypothesis_exists():
    from analyzer.render.ctrf import render_ctrf_report
    from analyzer.hypothesis import Hypothesis
    h = Hypothesis(
        cluster_id="C1",
        title="Endpoint moved",
        summary="Route renamed in recent commit",
        confidence=87,
        confidence_justification="git+logs",
        affected_tests=["test_a"],
        remediation=["Update URL in test"],
        buggy_location="api/routes.py:44",
    )
    result = _make_result(hypotheses=[h])
    parsed = json.loads(render_ctrf_report(result))
    test = parsed["results"]["tests"][0]
    assert "ai" in test
    assert "87" in test["ai"] or "87%" in test["ai"]


def test_ctrf_render_tool_name_is_correct():
    from analyzer.render.ctrf import render_ctrf_report
    result = _make_result(framework="jest")
    parsed = json.loads(render_ctrf_report(result))
    assert parsed["results"]["tool"]["name"] == "ai-test-failure-analyzer"


def test_ctrf_render_flaky_status_maps_to_other():
    """A failure with status='flaky' must produce CTRF status='other' and flaky=True."""
    from analyzer.render.ctrf import render_ctrf_report
    from analyzer.orchestrator import AnalysisResult
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    from analyzer.workspace_scanner import WorkspaceProfile
    f = NormalizedFailure(
        id=make_failure_id("playwright", "suite", "flaky_test", "test.spec.ts"),
        framework="playwright", suite="suite", title="flaky_test",
        file="test.spec.ts", status="flaky",
        error_message="Intermittent timeout",
        flakiness_score=0.8,
    )
    result = AnalysisResult(
        framework="playwright",
        failures=[f],
        git={"available": False, "commits": [], "summary": {}},
        logs={"available": False, "matches": [], "summary": {}},
        config={"available": False, "files": [], "summary": {}},
        matrix=[],
        clusters=[],
        hypotheses=[],
        report_markdown="# report",
        elapsed_seconds=1.0,
        profile=WorkspaceProfile(
            mode="FULL_SOURCE", source_roots=[], test_roots=[], noise_paths=[],
            openapi_spec=None, has_git=False,
        ),
        phase_timings={},
    )
    parsed = json.loads(render_ctrf_report(result))
    test = parsed["results"]["tests"][0]
    assert test["status"] == "other", f"Expected 'other', got {test['status']!r}"
    assert test.get("flaky") is True, "Expected flaky=True for flaky test"


def test_ctrf_render_summary_has_other_not_flaky():
    """Summary must have 'other' key, not 'flaky'."""
    from analyzer.render.ctrf import render_ctrf_report
    result = _make_result()
    parsed = json.loads(render_ctrf_report(result))
    summary = parsed["results"]["summary"]
    assert "other" in summary, "'other' key missing from summary"
    assert "flaky" not in summary, "'flaky' key must not appear in summary"
