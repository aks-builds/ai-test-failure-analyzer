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
