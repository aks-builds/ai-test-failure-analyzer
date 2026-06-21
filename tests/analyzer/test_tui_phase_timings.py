"""Tests for TUI phase timing display.

The TUI uses a helper function format_phase_line() to render each
phase completion line with optional ms suffix. We test that function
directly — no Textual app needed.
"""
from __future__ import annotations


def test_format_phase_line_with_timing():
    from analyzer.ui.tui import format_phase_line
    line = format_phase_line(phase=1, name="Collect failures", timing_seconds=0.123)
    assert "1" in line
    assert "Collect failures" in line
    assert "123ms" in line


def test_format_phase_line_without_timing():
    from analyzer.ui.tui import format_phase_line
    line = format_phase_line(phase=2, name="Read test intent", timing_seconds=0.0)
    assert "2" in line
    assert "Read test intent" in line
    # No ms suffix when timing is zero
    assert "ms" not in line


def test_format_phase_line_none_timing():
    from analyzer.ui.tui import format_phase_line
    line = format_phase_line(phase=6, name="Cross-correlate evidence", timing_seconds=None)
    assert "6" in line
    assert "Cross-correlate evidence" in line
    assert "ms" not in line


def test_format_phase_line_large_timing():
    from analyzer.ui.tui import format_phase_line
    line = format_phase_line(phase=5, name="Collect evidence", timing_seconds=1.5)
    assert "1500ms" in line


def test_format_phase_line_checkmark():
    from analyzer.ui.tui import format_phase_line
    line = format_phase_line(phase=7, name="Form hypotheses", timing_seconds=0.05)
    # Must include a checkmark symbol
    assert "✓" in line


def test_phase_timings_key_lookup():
    """phase_timings dict keys follow the pattern used in orchestrator."""
    # The orchestrator stores keys like "2.5_detect_flaky" and "5.5_collect_evidence".
    # The TUI constructs the key from event phase+name. Verify the helper handles
    # string phases (e.g. "2.5") without crashing.
    from analyzer.ui.tui import format_phase_line
    line = format_phase_line(phase="2.5", name="Detect flaky tests", timing_seconds=0.042)
    assert "2.5" in line
    assert "Detect flaky tests" in line
    assert "42ms" in line


def test_render_phase_timings_with_populated_result():
    """render_phase_timings iterates result.phase_timings and returns formatted lines."""
    from types import SimpleNamespace
    from analyzer.ui.tui import render_phase_timings

    result = SimpleNamespace(
        phase_timings={
            "0_scan_workspace": 0.045,
            "2.5_detect_flaky": 0.012,
            "5.5_collect_evidence": 0.300,
        }
    )
    output = render_phase_timings(result)

    # Each phase key should produce a line containing the phase number
    assert "0" in output
    assert "scan workspace" in output
    assert "45ms" in output

    assert "2.5" in output
    assert "detect flaky" in output
    assert "12ms" in output

    assert "5.5" in output
    assert "collect evidence" in output
    assert "300ms" in output

    # All lines must contain the checkmark
    for line in output.splitlines():
        assert "✓" in line

    # ms suffix must appear (at least one timing > 0)
    assert "ms" in output


def test_render_phase_timings_empty_returns_empty_string():
    """render_phase_timings returns '' when phase_timings is empty or absent."""
    from types import SimpleNamespace
    from analyzer.ui.tui import render_phase_timings

    assert render_phase_timings(SimpleNamespace(phase_timings={})) == ""
    assert render_phase_timings(SimpleNamespace()) == ""
