"""Markdown report renderer. Used for GitHub issues, web dashboard, file output."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..hypothesis import Hypothesis
from ..parsers.base import NormalizedFailure
from ..security import strip_html


def _confidence_bar(score: int) -> str:
    filled = round(score / 10)
    return "█" * filled + "░" * (10 - filled)


def render_markdown_report(
    failures: list[NormalizedFailure],
    hypotheses: list[Hypothesis],
    git: dict[str, Any] | None = None,
    logs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    framework: str = "",
    elapsed_seconds: float | None = None,
    run_url: str | None = None,
    profile: Any | None = None,
    no_app_fault: bool = False,
) -> str:
    failed = [f for f in failures if f.status == "failed"]
    passed = [f for f in failures if f.status == "passed"]

    lines: list[str] = []
    lines.append("# Test Failure Root-Cause Analysis")
    lines.append("")
    lines.append(f"_Generated at {datetime.now(timezone.utc).isoformat(timespec='seconds')}_")
    if run_url:
        lines.append(f"_CI run: {run_url}_")
    lines.append("")

    # Mode banner
    if profile is not None:
        if profile.mode == "API_ONLY":
            lines.append("> **API_ONLY mode** — no workspace source detected. Analyzing HTTP contract only.")
        else:
            src = ", ".join(p.name for p in profile.source_roots[:4]) if profile.source_roots else "—"
            lines.append(f"> **FULL_SOURCE mode** — scanned `{src}`, git history, logs, config.")
        lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Framework**: `{framework}`")
    lines.append(f"- **Tests**: {len(failures)} total · {len(failed)} failing · {len(passed)} passing")
    lines.append(f"- **Root-cause clusters**: {len(hypotheses)}")
    if elapsed_seconds is not None:
        lines.append(f"- **Analysis time**: {elapsed_seconds:.1f}s (vs ~30-60 min manual)")
    lines.append("- **Evidence sources consulted**:")
    lines.append(f"  - {'✅' if failures else '❌'} Test results")
    lines.append(f"  - {'✅' if git and git.get('available') else '❌'} Git history")
    lines.append(f"  - {'✅' if logs and logs.get('available') else '❌'} Application logs")
    lines.append(f"  - {'✅' if config and config.get('available') else '❌'} Environment config")
    lines.append("")

    # Failure triage table
    lines.append("## Failure Triage")
    lines.append("")
    if failed:
        lines.append("| # | Test | File | Got | Expected |")
        lines.append("|---|---|---|---|---|")
        for i, f in enumerate(failed, 1):
            got = (f.http or {}).get("status_got") or f.actual or "?"
            exp = (f.http or {}).get("status_expected") or f.expected or "?"
            lines.append(f"| {i} | {strip_html(f.title)} | `{f.file}{':'+str(f.line) if f.line else ''}` | {got} | {exp} |")
    else:
        lines.append("_No failing tests._")
    lines.append("")

    # Hypotheses
    lines.append("## Root-Cause Hypotheses")
    lines.append("")
    if not hypotheses:
        if no_app_fault:
            lines.append(
                "> ⚠ **No application-layer fault detected.** "
                "All candidate hypotheses were suppressed: either they lacked Tier-1 evidence "
                "(git/logs/config), or they matched fixture paths/intentional-failure markers. "
                "Check that the workspace contains source directories (`src/`, `app/`, `lib/`, `api/`) "
                "and that logs or git history cover the test run window."
            )
        else:
            lines.append("_No hypotheses generated. Either no failures, or insufficient signal to cluster._")
    for h in hypotheses:
        lines.append(f"### {h.cluster_id} — {h.title}")
        lines.append("")
        lines.append(f"**Confidence**: `{h.confidence}%` `{_confidence_bar(h.confidence)}` — _{h.confidence_justification}_")
        lines.append("")
        lines.append(h.summary)
        lines.append("")
        lines.append("**Affected tests**:")
        for t in h.affected_tests:
            lines.append(f"- ❌ {strip_html(t)}")
        lines.append("")
        lines.append("**Evidence chain**:")
        for ev in h.evidence_chain:
            icon = {
                "test_output": "🎭",
                "source_code": "📄",
                "git": "🔀",
                "logs": "📋",
                "config": "⚙️",
            }.get(ev.source, "•")
            lines.append(f"- {icon} **{ev.source}** `{strip_html(ev.ref)}` — {strip_html(ev.excerpt)[:160]}")
        lines.append("")
        if h.remediation:
            lines.append("**Remediation**:")
            for i, step in enumerate(h.remediation, 1):
                lines.append(f"{i}. {step}")
            lines.append("")
        if h.buggy_location:
            lines.append(f"**Buggy location**: `{h.buggy_location}`")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_This analysis was produced by the [ai-test-failure-analyzer]"
        "(https://github.com/aks-builds/ai-test-failure-analyzer)._"
    )
    return "\n".join(lines)


def render_issue_body(hypothesis: Hypothesis, run_url: str | None = None) -> str:
    """Render a single hypothesis as a GitHub issue body."""
    lines = [
        f"## {hypothesis.title}",
        "",
        f"**Cluster**: `{hypothesis.cluster_id}` · **Confidence**: `{hypothesis.confidence}%` `{_confidence_bar(hypothesis.confidence)}`",
        "",
        f"_{hypothesis.confidence_justification}_",
        "",
        "### Summary",
        hypothesis.summary,
        "",
        "### Affected tests",
    ]
    for t in hypothesis.affected_tests:
        lines.append(f"- ❌ {strip_html(t)}")
    lines.append("")
    lines.append("### Evidence chain")
    for ev in hypothesis.evidence_chain:
        icon = {
            "test_output": "🎭",
            "source_code": "📄",
            "git": "🔀",
            "logs": "📋",
            "config": "⚙️",
        }.get(ev.source, "•")
        lines.append(f"- {icon} **{ev.source}** `{strip_html(ev.ref)}` — {strip_html(ev.excerpt)[:160]}")
    lines.append("")
    lines.append("### Remediation")
    for i, step in enumerate(hypothesis.remediation, 1):
        lines.append(f"{i}. {step}")
    if hypothesis.buggy_location:
        lines.append("")
        lines.append(f"**Buggy location**: `{hypothesis.buggy_location}`")
    if run_url:
        lines.append("")
        lines.append(f"_CI run: {run_url}_")
    lines.append("")
    lines.append("---")
    lines.append("_Auto-triaged by the QA Test Failure Analyzer._")
    return "\n".join(lines)
