"""Interactive CLI — the `npm run analyze` entry point.

Uses ``questionary`` for prompts and ``rich`` for tables, progress bars, and
hypothesis cards. Wraps the orchestrator so the demo can show every phase
visibly.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import questionary
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from ..elicit import get as get_question
from ..github_integration import create_issue_from_hypothesis, detect_default_repo
from ..orchestrator import analyze
from ..render.ansi import render_ansi_report

PHASE_ICONS = {1: "📥", 2: "📖", 3: "🔀", 4: "📋", 5: "⚙️", 6: "🔗", 7: "🧠", 8: "📝"}


def _ask_cli(qid: str) -> str:
    """questionary-based ask callback. Renders the same Question objects as MCP elicitation."""
    q = get_question(qid)
    if q.free_form:
        ans = questionary.text(q.text, default=q.default or "").ask()
        return ans or ""
    return questionary.select(q.text, choices=q.choices, default=q.default).ask() or (q.default or "")


def run(
    results_path: str = "test-results/results.json",
    workspace: Optional[str] = None,
    framework: str = "auto",
    non_interactive: bool = False,
    create_issue: bool = False,
    repo: Optional[str] = None,
    out: Optional[str] = None,
    format: str = "markdown",
) -> int:
    """Run the CLI analysis flow. Returns exit code (0 = success)."""
    console = Console()
    ws = Path(workspace or Path.cwd()).resolve()

    console.print()
    console.rule("[bold cyan]🤖 QA Test Failure Analyzer", style="cyan")
    console.print(f"[dim]workspace:[/dim] {ws}")
    console.print(f"[dim]results:[/dim]   {results_path}")
    console.print(f"[dim]framework:[/dim] {framework}")
    console.print()

    # Phase progress display
    rows: dict[int, str] = {}

    def progress(event: dict) -> None:
        phase = event.get("phase")
        if not isinstance(phase, int):
            return
        name = event.get("name", "")
        status = event.get("status", "")
        icon = PHASE_ICONS.get(phase, "•")
        if status == "started":
            rows[phase] = f"{icon} Phase {phase}: {name}…"
            console.print(f"  [dim]{rows[phase]}[/dim]")
        elif status == "completed":
            data = event.get("data") or {}
            data_str = " ".join(f"[bold]{k}[/bold]={v}" for k, v in data.items())
            console.print(f"  [green]✓[/green] Phase {phase}: [bold]{name}[/bold]  {data_str}")

    ask = _ask_cli if not non_interactive else None

    try:
        result = analyze(
            results_path=results_path,
            workspace=ws,
            framework=framework,
            ask=ask,
            progress=progress,
        )
    except FileNotFoundError as e:
        console.print(f"\n[red]✗[/red] {e}")
        console.print("[dim]Run `npx playwright test` first (or check the path).[/dim]")
        return 2
    except Exception as e:
        console.print(f"\n[red]✗[/red] Analysis failed: {e}")
        return 1

    console.print()
    render_ansi_report(
        console,
        failures=result.failures,
        hypotheses=result.hypotheses,
        framework=result.framework,
        elapsed_seconds=result.elapsed_seconds,
        git=result.git,
        logs=result.logs,
        config=result.config,
    )

    # Optional output file
    if out:
        out_path = ws / out if not Path(out).is_absolute() else Path(out)
        out_path.write_text(result.report_markdown, encoding="utf-8")
        console.print(f"[green]✓[/green] Report written to [bold]{out_path}[/bold]")

    # Issue creation
    if result.hypotheses:
        should_create = create_issue
        if not non_interactive and not create_issue:
            ans = _ask_cli("confirm_create_issue")
            should_create = ans == "yes"

        if should_create:
            target_repo = repo or detect_default_repo()
            if not target_repo and not non_interactive:
                target_repo = _ask_cli("select_repo") or None
            if not target_repo:
                console.print("[yellow]![/yellow] No repo specified — skipping issue creation.")
            else:
                from ..config import github_token
                is_dry = not bool(github_token())
                if is_dry:
                    console.print("[dim](GITHUB_TOKEN not set — running in dry-run mode)[/dim]")
                top = result.hypotheses[0]
                issue_result = create_issue_from_hypothesis(
                    repo=target_repo, hypothesis=top, dry_run=is_dry,
                )
                if issue_result.get("created"):
                    console.print(f"[green]✓[/green] Issue created: {issue_result['url']}")
                elif issue_result.get("dry_run"):
                    console.print("[bold]Dry-run preview:[/bold]")
                    console.print(f"  repo:   {issue_result['would_create']['repo']}")
                    console.print(f"  title:  {issue_result['would_create']['title']}")
                    console.print(f"  labels: {', '.join(issue_result['would_create']['labels'])}")
                    console.print(f"  body:   {issue_result['would_create']['body_bytes']} bytes")
                else:
                    console.print(f"[red]✗[/red] {issue_result.get('reason', 'unknown')}")

    return 0
