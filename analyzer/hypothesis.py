"""Hypothesis formation and confidence scoring.

A hypothesis is one root-cause explanation that covers one cluster of failures.
Confidence is computed honestly from the evidence available; we never inflate
to "sound impressive" (per SKILL.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .parsers.base import NormalizedFailure


@dataclass
class EvidenceItem:
    source: str          # "test_output" | "source_code" | "git" | "logs" | "config"
    ref: str             # path/commit/log-line reference
    excerpt: str         # short snippet (will be truncated when rendered)


@dataclass
class Hypothesis:
    cluster_id: str
    title: str           # 1-line root cause
    summary: str         # 1-2 sentence explanation
    confidence: int      # 0-100
    confidence_justification: str
    affected_tests: list[str]
    evidence_chain: list[EvidenceItem] = field(default_factory=list)
    remediation: list[str] = field(default_factory=list)
    buggy_location: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "title": self.title,
            "summary": self.summary,
            "confidence": self.confidence,
            "confidence_justification": self.confidence_justification,
            "affected_tests": self.affected_tests,
            "evidence_chain": [e.__dict__ for e in self.evidence_chain],
            "remediation": self.remediation,
            "buggy_location": self.buggy_location,
        }


def _score(cluster: dict, has_git: bool, has_logs: bool, has_config: bool) -> tuple[int, str]:
    """Confidence scoring per the SKILL.md rubric."""
    sources = 1  # always have test output
    notes = ["test output observed"]
    if cluster.get("shared_commits") and has_git:
        sources += 1
        notes.append(f"{len(cluster['shared_commits'])} related commit(s)")
    if cluster.get("shared_risk_flags"):
        sources += 1
        notes.append(f"risk flags: {', '.join(cluster['shared_risk_flags'])}")
    if has_logs:
        sources += 1
        notes.append("log evidence available")
    if has_config:
        sources += 1
        notes.append("config evidence available")

    # 90-99: 4+ independent sources; 70-89: 3; 50-69: 2; 30-49: 1 with weak signal
    if sources >= 4:
        score = 90 + min(sources - 4, 8)
    elif sources == 3:
        score = 75
    elif sources == 2:
        score = 60
    else:
        # Single source — but did we at least see a clear pattern (e.g. 404 across endpoints)?
        score = 45 if cluster.get("size", 0) >= 2 else 35

    return score, " · ".join(notes)


def _diagnose_title(cluster: dict, failures: list[NormalizedFailure]) -> tuple[str, str, list[str]]:
    """Generate a human title, summary, and remediation steps.

    Heuristics, in order:
    - All failures share a 404 on different endpoints → endpoint rename / route restructure
    - All failures share a 404 on the same endpoint with a hardcoded ID → stale data / migration
    - All failures have non-HTTP errors → infra / dependency
    - Otherwise → generic
    """
    statuses = {f.http.get("status_got") for f in failures if f.http}
    expected = {f.http.get("status_expected") for f in failures if f.http}
    endpoints = sorted({f.http.get("url") for f in failures if f.http and f.http.get("url")})

    # Pattern: 404 across different endpoints
    if statuses == {404} and len(endpoints) >= 2:
        title = "Endpoint paths broken — likely route rename or restructure"
        summary = (
            f"All {len(failures)} affected tests receive 404 from previously-working endpoints "
            f"({', '.join(endpoints[:3])}{'…' if len(endpoints) > 3 else ''}). "
            "This pattern matches a deployment that renamed or moved API routes "
            "without a corresponding test update."
        )
        remediation = [
            "Inspect recent commits flagged endpoint_rename / breaking for the new path",
            "Update the failing tests with the new endpoint paths",
            "Consider an API versioning policy that fails CI on unversioned breaking changes",
        ]
        return title, summary, remediation

    if statuses == {404} and len(endpoints) == 1:
        title = "Stale hardcoded resource — record no longer exists"
        summary = (
            f"Tests are calling {endpoints[0]} expecting a 200 but receive 404. "
            "A hardcoded ID or fixture in the test almost certainly does not exist after a recent migration."
        )
        remediation = [
            "Replace hardcoded IDs with fixtures created in test setup",
            "Audit other tests for similar hardcoded references",
            "Coordinate test-data migrations with the data migration release notes",
        ]
        return title, summary, remediation

    # 401 / 403 cluster — auth
    if statuses <= {401, 403} and statuses:
        title = "Authentication or authorization regression"
        summary = (
            f"{len(failures)} tests are receiving {sorted(statuses)} where {sorted(expected) or '2xx'} was expected. "
            "An auth-service change has likely tightened or broken token handling."
        )
        remediation = [
            "Check recent auth-service / session changes",
            "Verify the test bearer tokens / cookies are still valid",
            "Roll back the auth change or update tests to provide the new auth shape",
        ]
        return title, summary, remediation

    # 5xx cluster — server side
    if any(s and s >= 500 for s in statuses):
        title = "Server-side errors during test run"
        summary = (
            f"{len(failures)} tests received 5xx responses. "
            "Application logs around the test run window should reveal the failure mode."
        )
        remediation = [
            "Read application logs for ERROR/FATAL lines at the test run timestamps",
            "Reproduce the failing endpoint locally with the same payload",
            "Roll back the most recent deploy if logs match a high-risk commit",
        ]
        return title, summary, remediation

    # Non-HTTP / generic
    title = f"Cluster of {len(failures)} related failures (root cause needs investigation)"
    summary = (
        "These tests share failure characteristics but the cause is not in any single evidence source. "
        "Inspect the affected source files and recent commits."
    )
    remediation = [
        "Read the affected test files for inline comments describing the regression",
        "Run the tests individually with --debug to capture richer context",
        "Bisect recent commits if symptoms appeared between two known-good runs",
    ]
    return title, summary, remediation


def form_hypotheses(
    failures: list[NormalizedFailure],
    clusters: list[dict],
    matrix: list[dict],
    git: dict | None,
    logs: dict | None,
    config: dict | None,
) -> list[Hypothesis]:
    """Produce one Hypothesis per cluster, ranked by size then confidence."""
    git = git or {}
    logs = logs or {}
    config = config or {}
    id_to_failure = {f.id: f for f in failures}
    id_to_row = {r["failure_id"]: r for r in matrix}

    out: list[Hypothesis] = []
    for cluster in clusters:
        cluster_failures = [id_to_failure[i] for i in cluster["failure_ids"] if i in id_to_failure]
        if not cluster_failures:
            continue

        title, summary, remediation = _diagnose_title(cluster, cluster_failures)
        confidence, justification = _score(
            cluster,
            has_git=git.get("available", False),
            has_logs=logs.get("available", False),
            has_config=config.get("available", False),
        )

        # Build the evidence chain
        chain: list[EvidenceItem] = []
        for f in cluster_failures[:3]:  # cap evidence excerpts per cluster
            if f.error_message:
                chain.append(EvidenceItem(
                    source="test_output",
                    ref=f"{f.file}:{f.line}" if f.line else f.file,
                    excerpt=(f.error_message or "")[:200],
                ))
        # Source-code excerpt: just reference the failing test file
        for f in cluster_failures[:2]:
            chain.append(EvidenceItem(
                source="source_code",
                ref=f"{f.file}:{f.line}",
                excerpt=f.title,
            ))
        # Git excerpt
        for commit_hash in cluster.get("shared_commits", [])[:2]:
            commit = next((c for c in git.get("commits", []) if c["hash"] == commit_hash), None)
            if commit:
                chain.append(EvidenceItem(
                    source="git",
                    ref=commit["hash"],
                    excerpt=commit["subject"],
                ))
        # Log excerpts attached at correlator time live in matrix rows; we keep counts only
        log_count = sum(id_to_row.get(i, {}).get("log_matches", 0) for i in cluster["failure_ids"])
        if log_count:
            chain.append(EvidenceItem(
                source="logs",
                ref=f"{log_count} matching log lines",
                excerpt="see log_scan output",
            ))
        # Config evidence (single marker; not per-cluster)
        if config.get("available"):
            chain.append(EvidenceItem(
                source="config",
                ref=", ".join(c["path"] for c in config.get("files", [])[:3]),
                excerpt="config snapshot available",
            ))

        buggy = None
        if cluster_failures:
            first = cluster_failures[0]
            buggy = f"{first.file}:{first.line}" if first.line else first.file

        out.append(
            Hypothesis(
                cluster_id=cluster["cluster_id"],
                title=title,
                summary=summary,
                confidence=confidence,
                confidence_justification=justification,
                affected_tests=[f.title for f in cluster_failures],
                evidence_chain=chain,
                remediation=remediation,
                buggy_location=buggy,
            )
        )

    # Rank: larger clusters first; tie-break by confidence
    out.sort(key=lambda h: (-len(h.affected_tests), -h.confidence))
    return out
