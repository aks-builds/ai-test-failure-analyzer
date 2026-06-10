"""The orchestrator — chains all eight phases of analysis into one generator.

Every UI surface (CLI / TUI / Web / MCP) calls this. The generator emits
progress events so each UI can render them in its own way without duplicating
analysis logic.

Event shapes:
    {"phase": int, "name": str, "status": "started"}
    {"phase": int, "name": str, "status": "completed", "data": <phase-specific>}
    {"phase": int, "name": str, "status": "question", "question": Question, "answer": Awaitable[str]}
    {"phase": "done", "report_markdown": str, "report_ansi": str, "hypotheses": list, ...}
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from .evidence import cluster_failures, correlate, scan_config, scan_git_history, scan_logs
from .hypothesis import Hypothesis, form_hypotheses
from .parsers import detect, parse
from .render.markdown import render_markdown_report
from .security import safe_path
from .workspace_scanner import WorkspaceProfile, scan_workspace
from .noise_filter import filter_hypotheses as _filter_hypotheses


@dataclass
class AnalysisResult:
    framework: str
    failures: list
    git: dict
    logs: dict
    config: dict
    matrix: list[dict]
    clusters: list[dict]
    hypotheses: list[Hypothesis]
    report_markdown: str
    elapsed_seconds: float
    profile: WorkspaceProfile | None = None
    suppressed_hypotheses: int = 0
    no_app_fault: bool = False


# An "ask" callback is what each UI provides for clarifying questions.
# It takes a Question id and returns the user's chosen answer (string).
AskFn = Callable[[str], str]


def _no_op_ask(qid: str) -> str:
    """Non-interactive fallback. Returns sensible defaults."""
    from .elicit import get
    q = get(qid)
    if q.default is not None:
        return q.default
    if q.choices:
        return q.choices[0]
    return ""


def analyze(
    results_path: str | Path,
    workspace: str | Path | None = None,
    framework: str = "auto",
    mode: str = "auto",
    ask: AskFn | None = None,
    progress: Callable[[dict], None] | None = None,
) -> AnalysisResult:
    """Run the full eight-phase analysis. Synchronous, with optional progress callback.

    Args:
        results_path: Path to the test results file (relative to workspace OK).
        workspace: Repo root. Defaults to CWD.
        framework: "auto" or one of the framework keys.
        mode: "auto" (scan workspace) or "api-only" (force API_ONLY).
        ask: Callback for clarifying questions. Defaults to non-interactive.
        progress: Callback invoked with phase progress dicts.
    """
    workspace = Path(workspace or Path.cwd()).resolve()
    ask = ask or _no_op_ask
    start = time.monotonic()

    def emit(event: dict) -> None:
        if progress:
            try:
                progress(event)
            except Exception:
                pass

    # ── Phase 0: Workspace scan ────────────────────────────────────────────────
    emit({"phase": 0, "name": "Scan workspace", "status": "started"})
    profile = scan_workspace(workspace, force_api_only=(mode == "api-only"))
    emit({
        "phase": 0, "name": "Scan workspace", "status": "completed",
        "data": {
            "mode": profile.mode,
            "source_roots": [str(p) for p in profile.source_roots],
            "noise_dirs": len(profile.noise_paths),
        },
    })

    # ── Phase 1: Collect failures ──────────────────────────────────────────
    emit({"phase": 1, "name": "Collect failures", "status": "started"})
    results_path = safe_path(workspace, results_path)
    if not results_path.exists():
        # Ask the user where the file is
        new = ask("results_path_missing")
        if new:
            results_path = safe_path(workspace, new)
    if not results_path.exists():
        raise FileNotFoundError(f"Test results not found: {results_path}")

    if framework == "auto":
        detected = detect(results_path)
        if detected is None:
            # Ask the user
            framework = ask("framework_ambiguous") or "playwright"

    detected_fw, failures = parse(results_path, framework=framework)
    emit({
        "phase": 1, "name": "Collect failures", "status": "completed",
        "data": {
            "framework": detected_fw,
            "total": len(failures),
            "failing": sum(1 for f in failures if f.status == "failed"),
            "passing": sum(1 for f in failures if f.status == "passed"),
        },
    })

    # ── Phase 2: Test intent — already in NormalizedFailure (file, line, comments-in-error). No separate call. ─
    emit({"phase": 2, "name": "Read test intent", "status": "completed", "data": {"failures_with_intent": sum(1 for f in failures if f.error_message)}})

    # ── Phase 3: Git history ───────────────────────────────────────────────
    emit({"phase": 3, "name": "Scan git history", "status": "started"})
    git = scan_git_history(workspace)
    if not git["available"]:
        # Confirm whether to continue
        choice = ask("no_git_history")
        if choice == "no":
            raise RuntimeError("Analysis cancelled — git history requested.")
    emit({"phase": 3, "name": "Scan git history", "status": "completed", "data": git["summary"]})

    # ── Phase 4: Logs ──────────────────────────────────────────────────────
    emit({"phase": 4, "name": "Scan application logs", "status": "started"})
    logs = scan_logs(workspace)
    emit({"phase": 4, "name": "Scan application logs", "status": "completed", "data": logs["summary"]})

    # ── Phase 5: Config ────────────────────────────────────────────────────
    emit({"phase": 5, "name": "Scan configuration", "status": "started"})
    config = scan_config(workspace)
    emit({"phase": 5, "name": "Scan configuration", "status": "completed", "data": config["summary"]})

    # ── Phase 6: Correlate ─────────────────────────────────────────────────
    emit({"phase": 6, "name": "Cross-correlate evidence", "status": "started"})
    correlation = correlate(failures, git, logs, config)
    clusters = cluster_failures(failures, correlation["matrix"])
    emit({"phase": 6, "name": "Cross-correlate evidence", "status": "completed", "data": {"clusters": len(clusters)}})

    # ── Phase 7: Form hypotheses ───────────────────────────────────────────
    emit({"phase": 7, "name": "Form hypotheses", "status": "started"})
    hypotheses_raw = form_hypotheses(failures, clusters, correlation["matrix"], git, logs, config)
    hypotheses, suppressed_count, no_app_fault = _filter_hypotheses(hypotheses_raw, profile)
    emit({
        "phase": 7, "name": "Form hypotheses", "status": "completed",
        "data": {
            "count": len(hypotheses),
            "suppressed": suppressed_count,
            "no_app_fault": no_app_fault,
        },
    })

    # ── Phase 8: Render report ─────────────────────────────────────────────
    elapsed = time.monotonic() - start
    emit({"phase": 8, "name": "Produce report", "status": "started"})
    report_md = render_markdown_report(
        failures=failures,
        hypotheses=hypotheses,
        git=git,
        logs=logs,
        config=config,
        framework=detected_fw,
        elapsed_seconds=elapsed,
        profile=profile,
        no_app_fault=no_app_fault,
    )
    emit({"phase": 8, "name": "Produce report", "status": "completed", "data": {"bytes": len(report_md)}})

    return AnalysisResult(
        framework=detected_fw,
        failures=failures,
        git=git,
        logs=logs,
        config=config,
        matrix=correlation["matrix"],
        clusters=clusters,
        hypotheses=hypotheses,
        report_markdown=report_md,
        elapsed_seconds=elapsed,
        profile=profile,
        suppressed_hypotheses=suppressed_count,
        no_app_fault=no_app_fault,
    )
