"""MCP server exposing the analyzer as discrete tools.

Built on the official ``mcp`` SDK using ``FastMCP``. Supports two transports:

- ``stdio`` — for local AI clients (Claude Code, Cursor, etc.)
- ``streamable-http`` — for remote clients (OpenAI, Gemini, any HTTP MCP client).
  Loopback-only by default; non-loopback bind requires ``ANALYZER_HTTP_TOKEN``.

Every tool returns a dict with an ``evidence`` field for explainability.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from . import __version__
from .config import github_repository, github_token, settings
from .elicit import QUESTIONS, get as get_question
from .evidence import cluster_failures, correlate, scan_config, scan_git_history, scan_logs
from .github_integration import create_issue_from_hypothesis
from .hypothesis import form_hypotheses
from .orchestrator import analyze as run_analyze
from .parsers import detect, parse
from .render.markdown import render_markdown_report

# Single FastMCP instance — name shows up in the MCP client picker
mcp = FastMCP(
    "ai-test-failure-analyzer",
    instructions=(
        "AI-assisted root-cause analysis for QA test failures. "
        "Supports Playwright, pytest, Jest/Vitest, and Cypress/WebdriverIO. "
        "Call `analyze` for the full ten-phase flow, or call individual phase tools "
        "(`collect_failures`, `scan_git_history`, etc.) for fine-grained control."
    ),
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _workspace() -> Path:
    return settings().workspace_root.resolve()


async def _elicit(ctx: Context, question_id: str) -> str:
    """Ask a clarifying question via MCP elicitation. Falls back to defaults if unsupported."""
    q = get_question(question_id)
    try:
        result = await ctx.elicit(message=q.text, schema=q.json_schema())
        if isinstance(result, dict) and "answer" in result:
            return str(result["answer"])
        # Some clients return the answer directly
        return str(result)
    except Exception:
        # Client doesn't support elicitation — use default
        return q.default or (q.choices[0] if q.choices else "")


# ── Tools (mapped to SKILL.md phases) ────────────────────────────────────────


@mcp.tool()
async def collect_failures(
    results_path: str,
    framework: str = "auto",
) -> dict[str, Any]:
    """Parse a test results file and return normalized failures (Phase 1).

    Args:
        results_path: Path to results file (relative to workspace or absolute).
        framework: "auto" (default) or one of: playwright, pytest, jest, vitest, cypress, webdriverio, junit.
    """
    path = _workspace() / results_path if not Path(results_path).is_absolute() else Path(results_path)
    detected_fw, failures = parse(path, framework=framework)
    return {
        "framework_detected": detected_fw,
        "summary": {
            "total": len(failures),
            "failed": sum(1 for f in failures if f.status == "failed"),
            "passed": sum(1 for f in failures if f.status == "passed"),
            "skipped": sum(1 for f in failures if f.status == "skipped"),
        },
        "failures": [f.to_dict() for f in failures],
        "evidence": [{"source": "test_output", "ref": str(path), "excerpt": f"parsed {len(failures)} test records"}],
    }


@mcp.tool()
async def read_test_intent(file: str, line: int | None = None) -> dict[str, Any]:
    """Read a spec file to extract the developer's intent (Phase 2).

    Returns the file's contents plus any inline comments around ``line``.
    """
    path = _workspace() / file if not Path(file).is_absolute() else Path(file)
    if not path.exists():
        return {"available": False, "reason": f"file not found: {file}"}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"available": False, "reason": str(e)}

    lines = content.splitlines()
    excerpt = None
    if line and 0 < line <= len(lines):
        start = max(0, line - 6)
        end = min(len(lines), line + 6)
        excerpt = "\n".join(f"{i+1}: {lines[i]}" for i in range(start, end))

    # Find inline comments — for TypeScript/JavaScript/Python style
    comments: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("//") or s.startswith("#") or s.startswith("*") or s.startswith("/*"):
            comments.append(s)

    return {
        "available": True,
        "file": file,
        "line": line,
        "excerpt": excerpt,
        "comments": comments[:50],
        "evidence": [{"source": "source_code", "ref": f"{file}:{line}" if line else file, "excerpt": "intent extracted"}],
    }


@mcp.tool()
async def scan_git_history_tool(since: str = "30 days ago", max_commits: int = 50) -> dict[str, Any]:
    """Collect recent git commits with risk flags (Phase 3)."""
    git = scan_git_history(_workspace(), since=since, max_commits=max_commits)
    git["evidence"] = [{"source": "git", "ref": "git log", "excerpt": f"{git['summary']['total']} commits, {git['summary']['high_risk']} high-risk"}]
    return git


@mcp.tool()
async def scan_logs_tool(paths: list[str] | None = None) -> dict[str, Any]:
    """Scan application logs for error-level lines (Phase 4)."""
    logs = scan_logs(_workspace(), paths=paths)
    logs["evidence"] = [{"source": "logs", "ref": "*.log", "excerpt": f"{logs['summary']['match_count']} matches across {logs['summary']['files_scanned']} files"}]
    return logs


@mcp.tool()
async def scan_config_tool() -> dict[str, Any]:
    """Scan environment and configuration files (Phase 5)."""
    cfg = scan_config(_workspace())
    cfg["evidence"] = [{"source": "config", "ref": "env/config files", "excerpt": f"{cfg['summary']['count']} config files read"}]
    return cfg


@mcp.tool()
async def correlate_evidence(
    failures: list[dict],
    git: dict | None = None,
    logs: dict | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Build a correlation matrix and failure clusters (Phase 6).

    ``failures`` should be the list of failure dicts from ``collect_failures``.
    """
    from .parsers.base import NormalizedFailure

    # Reconstruct typed failures from the dict input (MCP transport is JSON)
    typed = [NormalizedFailure(**{k: v for k, v in f.items() if k in NormalizedFailure.__annotations__}) for f in failures]
    matrix = correlate(typed, git, logs, config)
    clusters = cluster_failures(typed, matrix["matrix"])
    return {
        "matrix": matrix["matrix"],
        "clusters": clusters,
        "summary": matrix["summary"],
        "evidence": [{"source": "correlator", "ref": "matrix", "excerpt": f"{len(clusters)} clusters from {len(typed)} failures"}],
    }


@mcp.tool()
async def form_hypotheses_tool(
    failures: list[dict],
    clusters: list[dict],
    matrix: list[dict],
    git: dict | None = None,
    logs: dict | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Produce ranked hypotheses with confidence scores (Phase 7)."""
    from .parsers.base import NormalizedFailure

    typed = [NormalizedFailure(**{k: v for k, v in f.items() if k in NormalizedFailure.__annotations__}) for f in failures]
    hyps = form_hypotheses(typed, clusters, matrix, git, logs, config)
    return {
        "hypotheses": [h.to_dict() for h in hyps],
        "evidence": [{"source": "synthesis", "ref": "hypothesis-engine", "excerpt": f"{len(hyps)} hypotheses formed"}],
    }


@mcp.tool()
async def render_report(
    failures: list[dict],
    hypotheses: list[dict],
    format: str = "markdown",
    framework: str = "",
    git: dict | None = None,
    logs: dict | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Render the final report (Phase 8). ``format`` is ``markdown`` or ``json``."""
    from .hypothesis import EvidenceItem, Hypothesis
    from .parsers.base import NormalizedFailure

    typed_failures = [NormalizedFailure(**{k: v for k, v in f.items() if k in NormalizedFailure.__annotations__}) for f in failures]
    typed_hyps = []
    for h in hypotheses:
        evidence = [EvidenceItem(**e) for e in h.get("evidence_chain", [])]
        typed_hyps.append(
            Hypothesis(
                cluster_id=h["cluster_id"],
                title=h["title"],
                summary=h["summary"],
                confidence=h["confidence"],
                confidence_justification=h["confidence_justification"],
                affected_tests=h["affected_tests"],
                evidence_chain=evidence,
                remediation=h.get("remediation", []),
                buggy_location=h.get("buggy_location"),
            )
        )

    if format == "json":
        return {"format": "json", "report": {"failures": failures, "hypotheses": hypotheses}}

    md = render_markdown_report(
        failures=typed_failures,
        hypotheses=typed_hyps,
        git=git,
        logs=logs,
        config=config,
        framework=framework,
    )
    return {"format": "markdown", "report": md}


@mcp.tool()
async def create_github_issue(
    repo: str | None = None,
    hypothesis: dict | None = None,
    title: str | None = None,
    body_md: str | None = None,
    labels: list[str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Create a GitHub issue from a hypothesis.

    Either pass a ``hypothesis`` dict (preferred — full evidence chain included)
    or override with ``title`` + ``body_md``. ``repo`` defaults to ``GITHUB_REPOSITORY``.
    ``dry_run=True`` (default) returns what would be created without hitting GitHub.
    """
    target_repo = repo or github_repository()
    if not target_repo:
        return {"created": False, "reason": "no repo specified (pass repo or set GITHUB_REPOSITORY)"}

    from .hypothesis import EvidenceItem, Hypothesis

    typed: Hypothesis | None = None
    if hypothesis:
        evidence = [EvidenceItem(**e) for e in hypothesis.get("evidence_chain", [])]
        typed = Hypothesis(
            cluster_id=hypothesis["cluster_id"],
            title=hypothesis["title"],
            summary=hypothesis["summary"],
            confidence=hypothesis["confidence"],
            confidence_justification=hypothesis["confidence_justification"],
            affected_tests=hypothesis["affected_tests"],
            evidence_chain=evidence,
            remediation=hypothesis.get("remediation", []),
            buggy_location=hypothesis.get("buggy_location"),
        )

    return create_issue_from_hypothesis(
        repo=target_repo,
        hypothesis=typed,
        explicit_title=title,
        explicit_body=body_md,
        labels=labels or ["test-failure", "auto-triaged"],
        dry_run=dry_run,
    )


@mcp.tool()
async def analyze(
    ctx: Context,
    results_path: str = "test-results/results.json",
    framework: str = "auto",
    create_issue: bool = False,
    repo: str | None = None,
) -> dict[str, Any]:
    """Run the full ten-phase analysis end-to-end.

    Uses MCP elicitation for clarifying questions when the client supports it.
    """
    # Wire up elicitation
    answers: dict[str, str] = {}

    def ask(qid: str) -> str:
        # ctx.elicit is async; we marshal via the running loop
        if qid in answers:
            return answers[qid]
        loop = asyncio.get_event_loop()
        coro = _elicit(ctx, qid)
        try:
            ans = loop.run_until_complete(coro) if not loop.is_running() else asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=120)
        except Exception:
            from .elicit import get
            q = get(qid)
            ans = q.default or (q.choices[0] if q.choices else "")
        answers[qid] = ans
        return ans

    # Progress reporting via ctx.report_progress (best-effort)
    def progress(event: dict) -> None:
        try:
            phase = event.get("phase")
            name = event.get("name", "")
            status = event.get("status", "")
            ctx.info(f"Phase {phase} · {name} · {status}")
        except Exception:
            pass

    result = run_analyze(
        results_path=results_path,
        workspace=_workspace(),
        framework=framework,
        ask=ask,
        progress=progress,
    )

    response: dict[str, Any] = {
        "framework": result.framework,
        "summary": {
            "total": len(result.failures),
            "failed": sum(1 for f in result.failures if f.status == "failed"),
            "clusters": len(result.clusters),
            "hypotheses": len(result.hypotheses),
            "elapsed_seconds": result.elapsed_seconds,
        },
        "failures": [f.to_dict() for f in result.failures],
        "git_summary": result.git.get("summary"),
        "logs_summary": result.logs.get("summary"),
        "config_summary": result.config.get("summary"),
        "hypotheses": [h.to_dict() for h in result.hypotheses],
        "report_markdown": result.report_markdown,
    }

    if create_issue and result.hypotheses:
        top = result.hypotheses[0]
        issue_result = create_issue_from_hypothesis(
            repo=repo or github_repository() or "",
            hypothesis=top,
            labels=["test-failure", "auto-triaged"],
            dry_run=not bool(github_token()),
        )
        response["github_issue"] = issue_result

    return response


@mcp.tool()
async def list_questions() -> dict[str, Any]:
    """List the clarifying questions this server may ask via elicitation."""
    return {
        "questions": [
            {"id": q.id, "text": q.text, "choices": q.choices, "default": q.default, "free_form": q.free_form}
            for q in QUESTIONS.values()
        ],
    }


@mcp.tool()
async def server_info() -> dict[str, Any]:
    """Return server metadata — useful for debugging client integrations."""
    return {
        "name": "ai-test-failure-analyzer",
        "version": __version__,
        "workspace": str(_workspace()),
        "frameworks_supported": ["playwright", "pytest", "jest", "vitest", "cypress", "webdriverio", "junit"],
        "transports": ["stdio", "streamable-http"],
    }


# ── Transports ──────────────────────────────────────────────────────────────


def run_stdio() -> None:
    """Run the server over stdio. Default transport for local AI clients."""
    mcp.run()


def run_http(host: str | None = None, port: int | None = None) -> None:
    """Run the server over streamable-http.

    Loopback-only by default. If ``host`` is non-loopback, ``ANALYZER_HTTP_TOKEN``
    must be set and clients must send ``Authorization: Bearer <token>``.
    """
    s = settings()
    host = host or s.http_host
    port = port or s.http_port

    if host not in ("127.0.0.1", "localhost", "::1") and not s.http_token:
        raise RuntimeError(
            "Refusing to bind non-loopback address without ANALYZER_HTTP_TOKEN. "
            "Set the env var or bind to 127.0.0.1."
        )

    # FastMCP supports streamable-http via mcp.run(transport="streamable-http").
    # Some SDK versions also accept host/port kwargs.
    try:
        mcp.run(transport="streamable-http", host=host, port=port)
    except TypeError:
        # older SDK signature
        import os
        os.environ["MCP_HTTP_HOST"] = host
        os.environ["MCP_HTTP_PORT"] = str(port)
        mcp.run(transport="streamable-http")
