"""CLI dispatcher — the ``analyzer`` console script entry point.

Subcommands:
    analyzer analyze       Run full analysis (interactive)
    analyzer serve-stdio   Run MCP server over stdio
    analyzer serve-http    Run MCP server over streamable-http
    analyzer tui           Launch the Textual TUI
    analyzer web           Launch the FastAPI web dashboard
    analyzer info          Show server / framework info
"""

from __future__ import annotations

import sys
from typing import Optional

import typer

from . import __version__

app = typer.Typer(
    name="analyzer",
    help="QA Test Failure Analyzer — MCP server with CLI, TUI, and Web UIs.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ai-test-failure-analyzer {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(False, "--version", "-V", callback=_version_callback, is_eager=True),
) -> None:
    """QA Test Failure Analyzer."""


@app.command(name="analyze")
def cmd_analyze(
    results: str = typer.Option("test-results/results.json", "--results", "-r", help="Path to test results file"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root (defaults to CWD)"),
    framework: str = typer.Option("auto", "--framework", "-f", help="auto|playwright|pytest|jest|vitest|cypress|webdriverio|junit"),
    mode: str = typer.Option("auto", "--mode", "-m", help="auto|api-only (force API_ONLY mode)"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Disable clarifying questions"),
    create_issue: bool = typer.Option(False, "--create-issue", help="Create GitHub issue for top hypothesis"),
    repo: Optional[str] = typer.Option(None, "--repo", help="owner/repo for issue creation"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Write Markdown report to this path"),
    format: str = typer.Option("markdown", "--format", help="markdown|json|ctrf"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip reading and writing the analysis cache"),
    enrich: bool = typer.Option(False, "--enrich", help="Send top hypothesis to configured LLM for natural-language explanation "
                                "(requires ATFA_LLM_KEY or OPENAI_API_KEY)"),
) -> None:
    """Run the full ten-phase analysis (default subcommand)."""
    from .ui.cli import run

    code = run(
        results_path=results,
        workspace=workspace,
        framework=framework,
        mode=mode,
        non_interactive=non_interactive,
        create_issue=create_issue,
        repo=repo,
        out=out,
        format=format,
        no_cache=no_cache,
        enrich=enrich,
    )
    raise typer.Exit(code=code)


@app.command(name="watch")
def cmd_watch(
    results: str = typer.Option("test-results/results.json", "--results", "-r", help="Path to test results file"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root (defaults to CWD)"),
    framework: str = typer.Option("auto", "--framework", "-f", help="auto|playwright|pytest|jest|vitest|cypress|webdriverio|junit"),
    mode: str = typer.Option("auto", "--mode", "-m", help="auto|api-only (force API_ONLY mode)"),
    non_interactive: bool = typer.Option(True, "--non-interactive/--interactive", help="Disable clarifying questions"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Write Markdown report to this path"),
    format: str = typer.Option("markdown", "--format", help="markdown|json|ctrf"),
) -> None:
    """Watch results file and re-analyze on every change (2s polling, Ctrl-C to stop)."""
    import os as _os
    import time as _time
    from .ui.cli import run as _run

    results_path = results
    last_mtime = None
    typer.echo(f"Watching {results_path} — press Ctrl+C to stop")
    try:
        while True:
            try:
                mtime = _os.stat(results_path).st_mtime
            except OSError:
                _time.sleep(2)
                continue
            if mtime != last_mtime:
                last_mtime = mtime
                typer.echo("\n--- Change detected, re-analyzing ---")
                # Clear screen
                typer.echo("\033[2J\033[H", nl=False)
                _run(
                    results_path=results_path,
                    workspace=workspace,
                    framework=framework,
                    mode=mode,
                    non_interactive=non_interactive,
                    out=out,
                    format=format,
                    no_cache=True,  # always fresh in watch mode
                )
            _time.sleep(2)
    except KeyboardInterrupt:
        typer.echo("\nWatch mode stopped.")


@app.command(name="serve-stdio")
def cmd_serve_stdio() -> None:
    """Run the MCP server over stdio (for Claude Code, Cursor, etc.)."""
    from .server import run_stdio
    run_stdio()


@app.command(name="serve-http")
def cmd_serve_http(
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Bind address (loopback by default)"),
    port: int = typer.Option(8765, "--port", "-p", help="Bind port"),
) -> None:
    """Run the MCP server over streamable-http (for OpenAI/Gemini/web clients)."""
    from .server import run_http
    run_http(host=host, port=port)


@app.command(name="tui")
def cmd_tui(
    results: str = typer.Option("test-results/results.json", "--results", "-r"),
    framework: str = typer.Option("auto", "--framework", "-f"),
) -> None:
    """Launch the Textual TUI."""
    from .ui.tui import run as run_tui
    run_tui(results_path=results, framework=framework)


@app.command(name="web")
def cmd_web(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open browser automatically"),
) -> None:
    """Launch the FastAPI web dashboard."""
    from .ui.web.app import run as run_web
    run_web(host=host, port=port, open_browser=open_browser)


@app.command(name="info")
def cmd_info() -> None:
    """Show server / framework info."""
    from . import __version__
    from .parsers import FRAMEWORKS
    fw_list = ", ".join(sorted(FRAMEWORKS.keys()))
    typer.echo(f"ai-test-failure-analyzer {__version__}")
    typer.echo(f"Supported frameworks ({len(FRAMEWORKS)}): {fw_list}")
    typer.echo("Transports: stdio, streamable-http")


def main() -> None:
    """Setuptools entry point."""
    app()


if __name__ == "__main__":
    main()
