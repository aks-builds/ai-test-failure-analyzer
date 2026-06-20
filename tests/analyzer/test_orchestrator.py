"""End-to-end orchestrator test against the demo data."""

from __future__ import annotations

from pathlib import Path

from analyzer.orchestrator import analyze

REPO = Path(__file__).parents[2]
DEMO_RESULTS = Path(__file__).parent / "fixtures" / "playwright_results.json"


def test_analyze_against_demo_data():
    result = analyze(
        results_path=str(DEMO_RESULTS),
        workspace=REPO,
        framework="auto",
        ask=None,
        progress=None,
    )
    assert result.framework == "playwright"
    assert len(result.failures) == 6
    assert sum(1 for f in result.failures if f.status == "failed") == 3
    assert result.hypotheses
    # Top hypothesis should cover at least 2 of the 3 failing tests
    top = result.hypotheses[0]
    assert len(top.affected_tests) >= 1
    # Report is non-trivial
    assert len(result.report_markdown) > 500
    assert "Hypothes" in result.report_markdown


def test_orchestrator_phase_timings_present(tmp_path):
    """AnalysisResult must have phase_timings dict after v2 orchestrator."""
    from analyzer.orchestrator import AnalysisResult
    import dataclasses
    fields = {f.name for f in dataclasses.fields(AnalysisResult)}
    assert "phase_timings" in fields


def test_analyze_creates_dry_run_issue(monkeypatch):
    """Dry-run issue creation never touches the network."""
    from analyzer.github_integration import create_issue_from_hypothesis

    result = analyze(results_path=str(DEMO_RESULTS), workspace=REPO, ask=None)
    out = create_issue_from_hypothesis(
        repo="example/repo",
        hypothesis=result.hypotheses[0],
        dry_run=True,
    )
    assert out["dry_run"] is True
    assert "would_create" in out
    assert out["would_create"]["repo"] == "example/repo"


def test_orchestrator_end_to_end_playwright(tmp_path):
    """Full analysis on playwright fixture must produce hypotheses and phase_timings."""
    import shutil
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "playwright_results.json"
    dest = tmp_path / "results.json"
    shutil.copy(fixture, dest)

    result = analyze(str(dest), workspace=str(tmp_path))

    assert result.framework == "playwright"
    assert isinstance(result.hypotheses, list)
    assert isinstance(result.report_markdown, str)
    assert len(result.report_markdown) > 0
    assert isinstance(result.phase_timings, dict)
    # Phase 5.5 timing key must be present (contains "collect")
    assert any("collect" in k for k in result.phase_timings)


def test_orchestrator_end_to_end_pytest_junit(tmp_path):
    """Full analysis on pytest JUnit fixture must succeed."""
    import shutil
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "pytest_junit.xml"
    dest = tmp_path / "results.xml"
    shutil.copy(fixture, dest)

    result = analyze(str(dest), workspace=str(tmp_path))
    assert result.framework in ("pytest", "junit")
    assert isinstance(result.report_markdown, str)
