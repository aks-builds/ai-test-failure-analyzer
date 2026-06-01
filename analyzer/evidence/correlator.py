"""Cross-correlate failures with git/log/config evidence to discover root causes.

The output is two things:
1. A correlation matrix (one row per failure, one column per evidence source,
   with the strongest matching signal in each cell).
2. Failure clusters — groups of failures sharing a root cause signal.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from ..parsers.base import NormalizedFailure

# Patterns that link a failure to a code commit when the commit changes those terms.
ENDPOINT_PATH_RE = re.compile(r"(/[a-z0-9_\-/]+)", re.IGNORECASE)


def _extract_endpoint(failure: NormalizedFailure) -> str | None:
    if failure.http and failure.http.get("url"):
        return failure.http["url"]
    blob = "\n".join(filter(None, (failure.title, failure.error_message, failure.error_stack))) or ""
    m = ENDPOINT_PATH_RE.search(blob)
    return m.group(1) if m else None


def _find_related_commits(failure: NormalizedFailure, commits: list[dict]) -> list[dict]:
    """Return commits whose subject/files mention the failure's endpoint, file, or assertion target."""
    keywords: set[str] = set()
    if failure.file:
        keywords.add(failure.file.split("/")[-1].lower())
    ep = _extract_endpoint(failure)
    if ep:
        # Each non-trivial path segment is a search term
        for seg in ep.strip("/").split("/"):
            if len(seg) >= 3:
                keywords.add(seg.lower())

    related = []
    for c in commits:
        blob = (c.get("subject", "") + " " + " ".join(c.get("files", []))).lower()
        if any(k in blob for k in keywords):
            related.append(c)
    return related


def _find_related_logs(failure: NormalizedFailure, log_matches: list[dict]) -> list[dict]:
    ep = _extract_endpoint(failure) or ""
    title_words = {w.lower() for w in failure.title.split() if len(w) >= 4}
    related = []
    for m in log_matches:
        text = m.get("text", "").lower()
        if ep and ep.lower() in text:
            related.append(m)
        elif any(w in text for w in title_words):
            related.append(m)
    return related[:5]  # cap per failure


def correlate(
    failures: list[NormalizedFailure],
    git: dict[str, Any] | None = None,
    logs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the correlation matrix for a list of failures."""
    git = git or {"available": False, "commits": []}
    logs = logs or {"available": False, "matches": []}
    config = config or {"available": False, "files": []}

    only_failed = [f for f in failures if f.status in ("failed", "flaky")]

    rows = []
    for f in only_failed:
        endpoint = _extract_endpoint(f)
        related_commits = _find_related_commits(f, git.get("commits", []))
        related_logs = _find_related_logs(f, logs.get("matches", []))
        has_inline_comment = bool(f.error_message)

        # Status — prefer parsed http, fall back to actual/expected (strings that look like ints)
        status_got = f.http.get("status_got") if f.http else None
        status_exp = f.http.get("status_expected") if f.http else None
        if status_got is None and f.actual and f.actual.isdigit():
            status_got = int(f.actual)
        if status_exp is None and f.expected and f.expected.isdigit():
            status_exp = int(f.expected)

        rows.append({
            "failure_id": f.id,
            "test": f.title,
            "endpoint": endpoint,
            "status": status_got,
            "expected_status": status_exp,
            "code_comment": has_inline_comment,
            "git_commits": [c["hash"] for c in related_commits],
            "git_risk_flags": sorted({flag for c in related_commits for flag in c.get("risk_flags", [])}),
            "log_matches": len(related_logs),
            "config_signal": config.get("available", False),
        })

    return {
        "matrix": rows,
        "summary": {
            "failures": len(only_failed),
            "git_available": git.get("available", False),
            "logs_available": logs.get("available", False),
            "config_available": config.get("available", False),
        },
    }


def cluster_failures(
    failures: list[NormalizedFailure],
    matrix_rows: list[dict],
) -> list[dict[str, Any]]:
    """Group failures that share a root cause signal.

    Two failures are clustered together when they share any of:
    - the same root path segment under a 404 (endpoint rename pattern)
    - the same git commit in related_commits
    - the same risk flag with the same expected/got HTTP status combo
    """
    id_to_row = {r["failure_id"]: r for r in matrix_rows}
    id_to_failure = {f.id: f for f in failures}

    # Signature builder: a tuple of high-signal traits.
    # Primary signal is the (got, expected-class) status pair — a fleet of tests
    # all getting 404 vs an expected 2xx is the same root cause, regardless of endpoint.
    def signature(row: dict) -> tuple:
        got = row.get("status")
        exp = row.get("expected_status")
        exp_class = (exp // 100) if isinstance(exp, int) else None
        commits = tuple(sorted(row.get("git_commits", [])))
        risks = tuple(sorted(row.get("git_risk_flags", [])))
        return (got, exp_class, commits, risks)

    # Group strictly identical signatures first
    groups: dict[tuple, list[str]] = defaultdict(list)
    for r in matrix_rows:
        groups[signature(r)].append(r["failure_id"])

    # Merge groups that share at least one commit hash (transitive)
    merged: list[list[str]] = []
    used_signatures: set[tuple] = set()
    sig_list = list(groups.items())
    for i, (sig, ids) in enumerate(sig_list):
        if sig in used_signatures:
            continue
        bucket = list(ids)
        used_signatures.add(sig)
        sig_commits = sig[2]  # commits is the 3rd tuple element
        for sig2, ids2 in sig_list[i + 1 :]:
            if sig2 in used_signatures:
                continue
            sig2_commits = sig2[2]
            if set(sig_commits) & set(sig2_commits) and sig_commits:
                bucket.extend(ids2)
                used_signatures.add(sig2)
        merged.append(bucket)

    clusters = []
    for idx, ids in enumerate(merged, start=1):
        rows = [id_to_row[i] for i in ids if i in id_to_row]
        failures_in_cluster = [id_to_failure[i] for i in ids if i in id_to_failure]
        shared_commits = sorted({h for r in rows for h in r.get("git_commits", [])})
        shared_risks = sorted({h for r in rows for h in r.get("git_risk_flags", [])})
        endpoints = sorted({r.get("endpoint") for r in rows if r.get("endpoint")})
        clusters.append({
            "cluster_id": f"C{idx}",
            "failure_ids": ids,
            "failure_titles": [f.title for f in failures_in_cluster],
            "shared_commits": shared_commits,
            "shared_risk_flags": shared_risks,
            "endpoints": endpoints,
            "size": len(ids),
        })

    # Order by size desc — biggest impact first
    clusters.sort(key=lambda c: c["size"], reverse=True)
    return clusters
