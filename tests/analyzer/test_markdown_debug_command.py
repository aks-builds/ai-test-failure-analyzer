"""Tests that render_markdown_report includes a framework-specific debug command."""
from __future__ import annotations

from analyzer.render.markdown import render_markdown_report
from analyzer.hypothesis import Hypothesis, EvidenceItem
from analyzer.parsers.base import NormalizedFailure


def _make_failure(fid: str = "f1") -> NormalizedFailure:
    return NormalizedFailure(
        id=fid,
        framework="playwright",
        suite="Login",
        title="Login page fails to load",
        status="failed",
        file="tests/login.spec.ts",
        line=10,
        error_message="Expected 200, got 404",
    )


def _make_hypothesis() -> Hypothesis:
    return Hypothesis(
        cluster_id="C1",
        title="Test hypothesis",
        summary="Something broke.",
        confidence=75,
        confidence_justification="test output observed",
        affected_tests=["Login page fails to load"],
        evidence_chain=[
            EvidenceItem(source="test_output", ref="tests/login.spec.ts:10", excerpt="Expected 200, got 404")
        ],
        remediation=["Check routes", "Rerun with debug"],
    )


def test_render_includes_playwright_debug_command():
    report = render_markdown_report(
        failures=[_make_failure()],
        hypotheses=[_make_hypothesis()],
        framework="playwright",
    )
    assert "Debug command" in report
    assert "playwright" in report.lower()


def test_render_includes_pytest_debug_command():
    report = render_markdown_report(
        failures=[_make_failure()],
        hypotheses=[_make_hypothesis()],
        framework="pytest",
    )
    assert "Debug command" in report
    assert "pytest" in report.lower()


def test_render_no_debug_command_for_unknown_framework():
    """When framework has no run command mapping, no Debug command line should appear."""
    report = render_markdown_report(
        failures=[_make_failure()],
        hypotheses=[_make_hypothesis()],
        framework="unknown_fw",
    )
    assert "Debug command" not in report


def test_render_no_debug_command_when_no_framework():
    """Empty framework string should not produce a Debug command line."""
    report = render_markdown_report(
        failures=[_make_failure()],
        hypotheses=[_make_hypothesis()],
        framework="",
    )
    assert "Debug command" not in report


def test_render_jest_debug_command():
    report = render_markdown_report(
        failures=[_make_failure()],
        hypotheses=[_make_hypothesis()],
        framework="jest",
    )
    assert "Debug command" in report
    assert "jest" in report.lower()
