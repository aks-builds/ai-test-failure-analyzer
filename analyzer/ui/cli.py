"""Interactive CLI — the `npm run analyze` entry point.

Uses ``questionary`` for prompts and ``rich`` for tables, progress bars, and
hypothesis cards. Wraps the orchestrator so the demo can show every phase
visibly.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
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
from ..security import SecurityError

PHASE_ICONS = {1: "📥", 2: "📖", "2.5": "🔍", 3: "🔀", 4: "📋", 5: "⚙️", "5.5": "🔬", 6: "🔗", 7: "🧠", 8: "📝"}

_VALID_FORMATS = {"markdown", "json", "ctrf"}
_VALID_MODES = {"auto", "api-only"}


def _validate_inputs(
    results_path: str,
    workspace: Optional[str],
    framework: str,
    mode: str,
    repo: Optional[str],
    out: Optional[str],
    format: str,
    console: Console,
) -> "int | None":
    """Validate all CLI inputs before calling analyze(). Returns 2 on failure, None on success."""
    if format not in _VALID_FORMATS:
        console.print(f"\n[red]✗[/red] Invalid --format {format!r}")
        console.print(f"  Supported values: {', '.join(sorted(_VALID_FORMATS))}")
        return 2

    if mode not in _VALID_MODES:
        console.print(f"\n[red]✗[/red] Invalid --mode {mode!r}")
        console.print(f"  Supported values: {', '.join(sorted(_VALID_MODES))}")
        return 2

    if workspace is not None:
        ws_path = Path(workspace)
        if not ws_path.exists() or not ws_path.is_dir():
            console.print(f"\n[red]✗[/red] Workspace directory not found: {workspace}")
            console.print(
                "  Pass --workspace pointing to your repository root, "
                "or omit it to use the current directory."
            )
            return 2

    if out is not None:
        out_parent = Path(out).resolve().parent
        if not out_parent.exists():
            console.print(f"\n[red]✗[/red] Output directory does not exist: {out_parent}")
            console.print(
                "  Create the directory first, or use a path in an existing directory."
            )
            return 2

    if repo is not None:
        parts = repo.split("/")
        if not (len(parts) == 2 and all(parts)):
            console.print(f"\n[red]✗[/red] Invalid --repo format: {repo!r}")
            console.print("  Expected: owner/repo  (e.g. acme-corp/my-api-service)")
            return 2

    if framework != "auto":
        from ..parsers import FRAMEWORKS
        valid = {"auto"} | set(FRAMEWORKS.keys())
        if framework not in valid:
            console.print(f"\n[red]✗[/red] Unknown --framework {framework!r}")
            console.print(f"  Supported: {', '.join(sorted(valid))}")
            return 2

    return None


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
    mode: str = "auto",
    non_interactive: bool = False,
    create_issue: bool = False,
    repo: Optional[str] = None,
    out: Optional[str] = None,
    format: str = "markdown",
    no_cache: bool = False,
    enrich: bool = False,
) -> int:
    """Run the CLI analysis flow. Returns exit code (0 = success)."""
    console = Console()
    ws = Path(workspace or Path.cwd()).resolve()

    _err = _validate_inputs(
        results_path=results_path,
        workspace=workspace,
        framework=framework,
        mode=mode,
        repo=repo,
        out=out,
        format=format,
        console=console,
    )
    if _err is not None:
        return _err

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
        if not isinstance(phase, (int, str)):
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
            mode=mode,
            ask=ask,
            progress=progress,
            no_cache=no_cache,
        )
    except FileNotFoundError as e:
        console.print(f"\n[red]✗[/red] {e}")
        console.print("[dim]Run your test suite first to generate a results file, then re-run.[/dim]")
        return 2
    except ValueError as e:
        console.print(f"\n[red]✗ Validation error[/red]")
        for line in str(e).splitlines():
            console.print(f"  {line}")
        return 2
    except SecurityError as e:
        console.print(f"\n[red]✗ Security error[/red]  {e}")
        console.print("[dim]Results file path must be inside the workspace directory.[/dim]")
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

    # Optional LLM enrichment
    if enrich:
        from ..enricher import enrich as _enrich, EnrichConfig
        try:
            enrich_config = EnrichConfig.from_env()
            enrichment = _enrich(result, enrich_config)
            if enrichment:
                result.report_markdown += "\n\n" + enrichment
                console.print("\n[bold cyan]── LLM Enrichment ──[/bold cyan]")
                console.print(enrichment)
        except ValueError as e:
            print(f"  {e}", file=sys.stderr)

    # Optional output file / format handling
    if format == "ctrf" or (out and out.endswith(".ctrf.json")):
        from ..render.ctrf import render_ctrf_report
        output = render_ctrf_report(result)
        if out:
            out_path = ws / out if not Path(out).is_absolute() else Path(out)
            out_path.write_text(output, encoding="utf-8")
            console.print(f"[green]✓[/green] CTRF report written to [bold]{out_path}[/bold]")
        else:
            print(output)
    elif format == "json":
        import json as _json
        output = _json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
        if out:
            out_path = ws / out if not Path(out).is_absolute() else Path(out)
            out_path.write_text(output, encoding="utf-8")
            console.print(f"[green]✓[/green] JSON report written to [bold]{out_path}[/bold]")
        else:
            print(output)
    elif out:
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
