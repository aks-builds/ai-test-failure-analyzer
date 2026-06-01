"""Textual TUI for the analyzer.

Three screens (tabs):
1. Triage — DataTable of failures
2. Evidence — tabs for source / git / logs / config
3. Hypotheses — cards with confidence bars

Hotkeys: r=rerun · g=create-issue · q=quit
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    Static,
    TabbedContent,
    TabPane,
)

from ..config import github_token
from ..github_integration import create_issue_from_hypothesis, detect_default_repo
from ..orchestrator import AnalysisResult, analyze


class IssueModal(ModalScreen[bool]):
    """Modal for creating a GitHub issue from the top hypothesis."""

    CSS = """
    IssueModal {
        align: center middle;
    }
    #dialog {
        width: 70;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, result: AnalysisResult) -> None:
        super().__init__()
        self.result = result

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label("[bold]Create GitHub Issue[/bold]", id="title")
            yield Label(f"Top hypothesis: {self.result.hypotheses[0].title if self.result.hypotheses else '(none)'}")
            yield Label("Repository (owner/repo):")
            yield Input(value=detect_default_repo() or "", id="repo")
            with Horizontal():
                yield Button("Create (dry-run)", id="dry", variant="primary")
                yield Button("Create (live)", id="live", variant="success")
                yield Button("Cancel", id="cancel", variant="default")
            yield Static("", id="result")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(False)
            return
        if not self.result.hypotheses:
            self.query_one("#result", Static).update("[red]No hypotheses to file.[/red]")
            return
        repo = self.query_one("#repo", Input).value.strip()
        if not repo:
            self.query_one("#result", Static).update("[red]Repo is required.[/red]")
            return
        is_dry = event.button.id == "dry" or not github_token()
        out = create_issue_from_hypothesis(
            repo=repo, hypothesis=self.result.hypotheses[0], dry_run=is_dry,
        )
        if out.get("created"):
            self.query_one("#result", Static).update(f"[green]Created: {out['url']}[/green]")
        elif out.get("dry_run"):
            wc = out["would_create"]
            self.query_one("#result", Static).update(
                f"[yellow]Dry-run: would create '{wc['title']}' on {wc['repo']}[/yellow]"
            )
        else:
            self.query_one("#result", Static).update(f"[red]{out.get('reason', 'failed')}[/red]")


class AnalyzerApp(App):
    """Three-screen TUI for the analyzer."""

    CSS = """
    Screen {
        background: $surface;
    }
    #status {
        height: 1;
        background: $panel;
        padding: 0 1;
        color: $text-muted;
    }
    .card {
        border: round $accent;
        padding: 0 1;
        margin: 1 0;
    }
    """

    BINDINGS = [
        Binding("r", "rerun", "Rerun"),
        Binding("g", "create_issue", "Create issue"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, results_path: str, framework: str = "auto") -> None:
        super().__init__()
        self.results_path = results_path
        self.framework = framework
        self.result: AnalysisResult | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Loading analysis…", id="status")
        with TabbedContent(initial="tab-triage"):
            with TabPane("Triage", id="tab-triage"):
                yield DataTable(id="triage")
            with TabPane("Evidence", id="tab-evidence"):
                with TabbedContent(initial="ev-source"):
                    with TabPane("Source", id="ev-source"):
                        yield VerticalScroll(Static("", id="ev-source-content"))
                    with TabPane("Git", id="ev-git"):
                        yield VerticalScroll(Static("", id="ev-git-content"))
                    with TabPane("Logs", id="ev-logs"):
                        yield VerticalScroll(Static("", id="ev-logs-content"))
                    with TabPane("Config", id="ev-config"):
                        yield VerticalScroll(Static("", id="ev-config-content"))
            with TabPane("Hypotheses", id="tab-hypotheses"):
                yield VerticalScroll(id="hyp-list")
        yield Footer()

    def on_mount(self) -> None:
        # DataTable columns
        table = self.query_one("#triage", DataTable)
        table.add_columns("#", "Test", "File", "Got", "Expected")
        self._refresh()

    def _refresh(self) -> None:
        self.query_one("#status", Static).update("[yellow]Analyzing…[/yellow]")
        try:
            self.result = analyze(
                results_path=self.results_path,
                framework=self.framework,
                ask=None,
                progress=None,
            )
        except Exception as e:
            self.query_one("#status", Static).update(f"[red]Analysis failed: {e}[/red]")
            return

        # Status bar
        r = self.result
        failed = sum(1 for f in r.failures if f.status == "failed")
        self.query_one("#status", Static).update(
            f"[bold cyan]{r.framework}[/bold cyan] · "
            f"{len(r.failures)} tests · [red]{failed} failing[/red] · "
            f"{len(r.hypotheses)} hypotheses · {r.elapsed_seconds:.1f}s"
        )

        # Triage table
        table = self.query_one("#triage", DataTable)
        table.clear()
        for i, f in enumerate((x for x in r.failures if x.status == "failed"), 1):
            got = str((f.http or {}).get("status_got") or f.actual or "?")
            exp = str((f.http or {}).get("status_expected") or f.expected or "?")
            location = f"{f.file}{':'+str(f.line) if f.line else ''}"
            table.add_row(str(i), f.title[:60], location[:50], got, exp)

        # Evidence panels
        self.query_one("#ev-source-content", Static).update(
            "\n\n".join(
                f"[bold]{f.file}:{f.line}[/bold]\n{f.title}\n[dim]{f.error_message or ''}[/dim]"
                for f in r.failures if f.status == "failed"
            ) or "No failing tests."
        )
        self.query_one("#ev-git-content", Static).update(
            (f"[dim]since: {r.git.get('since', '?')}, commits: {r.git['summary']['total']}, high-risk: {r.git['summary']['high_risk']}[/dim]\n\n" +
             "\n".join(f"[bold]{c['hash']}[/bold] {c['subject']}  [dim]{', '.join(c.get('risk_flags') or []) or 'no flags'}[/dim]"
                       for c in r.git.get("commits", [])[:30]))
            if r.git.get("available") else "[dim]No git history available.[/dim]"
        )
        self.query_one("#ev-logs-content", Static).update(
            "\n".join(f"[bold]{m['file']}:{m['line_no']}[/bold] [{m['level']}] {m['text']}" for m in r.logs.get("matches", [])[:50])
            if r.logs.get("available") else "[dim]No log files found.[/dim]"
        )
        self.query_one("#ev-config-content", Static).update(
            "\n\n".join(f"[bold]{c['path']}[/bold] ({c['size_bytes']}B)\n[dim]{c['excerpt'][:400]}[/dim]" for c in r.config.get("files", []))
            if r.config.get("available") else "[dim]No config files found.[/dim]"
        )

        # Hypotheses
        hyp_container = self.query_one("#hyp-list", VerticalScroll)
        for child in list(hyp_container.children):
            child.remove()
        for h in r.hypotheses:
            card = Static(
                f"[bold]{h.cluster_id} — {h.title}[/bold]\n"
                f"Confidence: [yellow]{h.confidence}%[/yellow]  [dim]({h.confidence_justification})[/dim]\n\n"
                f"{h.summary}\n\n"
                f"[bold]Affected:[/bold]\n" +
                "\n".join(f"  ❌ {t}" for t in h.affected_tests) +
                "\n\n[bold]Remediation:[/bold]\n" +
                "\n".join(f"  {i+1}. {s}" for i, s in enumerate(h.remediation)),
                classes="card",
            )
            hyp_container.mount(card)

    def action_rerun(self) -> None:
        self._refresh()

    def action_create_issue(self) -> None:
        if not self.result:
            return
        self.push_screen(IssueModal(self.result))


def run(results_path: str = "test-results/results.json", framework: str = "auto") -> None:
    AnalyzerApp(results_path=results_path, framework=framework).run()


if __name__ == "__main__":
    run()
