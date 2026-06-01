"""Rich-formatted terminal renderer for the CLI UI."""

from __future__ import annotations

from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from ..hypothesis import Hypothesis
from ..parsers.base import NormalizedFailure


def _confidence_color(score: int) -> str:
    if score >= 90:
        return "bright_green"
    if score >= 70:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def render_ansi_report(
    console: Console,
    failures: list[NormalizedFailure],
    hypotheses: list[Hypothesis],
    framework: str = "",
    elapsed_seconds: float | None = None,
    git: dict[str, Any] | None = None,
    logs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> None:
    """Print the full ANSI report to ``console``."""
    failed = [f for f in failures if f.status == "failed"]
    passed = [f for f in failures if f.status == "passed"]

    # Header
    console.rule("[bold cyan]Test Failure Root-Cause Analysis", style="cyan")
    summary = Text()
    summary.append("Framework: ", style="dim")
    summary.append(f"{framework or 'unknown'}\n", style="bold")
    summary.append("Tests:     ", style="dim")
    summary.append(f"{len(failures)} total · ", style="bold")
    summary.append(f"{len(failed)} failing", style="red bold")
    summary.append(" · ")
    summary.append(f"{len(passed)} passing\n", style="green")
    summary.append("Clusters:  ", style="dim")
    summary.append(f"{len(hypotheses)}\n", style="bold")
    if elapsed_seconds is not None:
        summary.append("Time:      ", style="dim")
        summary.append(f"{elapsed_seconds:.1f}s", style="bold")
        summary.append("  (vs ~30-60 min manual)", style="dim")
        summary.append("\n")

    sources = [
        ("Test results", True),
        ("Git history", bool(git and git.get("available"))),
        ("Application logs", bool(logs and logs.get("available"))),
        ("Config snapshot", bool(config and config.get("available"))),
    ]
    summary.append("Sources:   ", style="dim")
    for i, (name, ok) in enumerate(sources):
        summary.append("✓ " if ok else "○ ", style="green" if ok else "red")
        summary.append(name)
        if i < len(sources) - 1:
            summary.append("  ")
    console.print(summary)
    console.print()

    # Triage table
    table = Table(title="Failure Triage", show_lines=False, expand=False, title_style="bold yellow")
    table.add_column("#", style="dim", width=3)
    table.add_column("Test", overflow="fold")
    table.add_column("File", style="cyan", overflow="fold")
    table.add_column("Got", style="red", justify="right")
    table.add_column("Expected", style="green", justify="right")
    for i, f in enumerate(failed, 1):
        got = str((f.http or {}).get("status_got") or f.actual or "?")
        exp = str((f.http or {}).get("status_expected") or f.expected or "?")
        location = f"{f.file}{':'+str(f.line) if f.line else ''}"
        table.add_row(str(i), f.title, location, got, exp)
    console.print(table)
    console.print()

    # Hypotheses
    for h in hypotheses:
        color = _confidence_color(h.confidence)
        header = Text()
        header.append(f"{h.cluster_id} — ", style="bold")
        header.append(h.title, style="bold bright_white")
        header.append("\n")
        header.append("Confidence: ", style="dim")
        header.append(f"{h.confidence}%  ", style=f"{color} bold")
        bar = ProgressBar(total=100, completed=h.confidence, width=20, complete_style=color)
        header.append("\n")
        header.append("Why: ", style="dim")
        header.append(h.confidence_justification, style="italic")
        header.append("\n\n")
        header.append(h.summary)
        header.append("\n\nAffected tests:\n", style="bold")
        for t in h.affected_tests:
            header.append(f"  ❌ {t}\n", style="red")

        header.append("\nEvidence chain:\n", style="bold")
        for ev in h.evidence_chain:
            icon = {"test_output": "🎭", "source_code": "📄", "git": "🔀", "logs": "📋", "config": "⚙️"}.get(ev.source, "•")
            header.append(f"  {icon} ", style="dim")
            header.append(f"{ev.source} ", style="cyan")
            header.append(f"{ev.ref}", style="dim")
            header.append(f"  {ev.excerpt[:140]}\n")

        header.append("\nRemediation:\n", style="bold")
        for i, step in enumerate(h.remediation, 1):
            header.append(f"  {i}. {step}\n")

        if h.buggy_location:
            header.append("\nBuggy location: ", style="dim")
            header.append(h.buggy_location, style="bold cyan")

        panel = Panel(
            Group(header, bar),
            title=f"[{color}]{h.cluster_id}[/{color}]",
            border_style=color,
            padding=(1, 2),
        )
        console.print(panel)
        console.print()
