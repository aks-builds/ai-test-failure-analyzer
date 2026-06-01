"""Bounded, safe git history scanner.

All subprocess calls use a list[str] (never shell=True), use a whitelisted
subcommand, and validate commit hashes against a strict regex. Output is
capped at MAX_GIT_COMMITS commits.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from ..security import MAX_GIT_COMMITS, validate_git_args

# Risk patterns: when a commit message or filename matches one of these,
# we flag the commit as HIGH RISK for test failures.
RISK_PATTERNS = {
    "endpoint_rename": re.compile(r"\b(rename|move|restructure|refactor).{0,30}(route|endpoint|api|path)\b", re.IGNORECASE),
    "migration": re.compile(r"\b(migration|migrate|schema|drop|alter|purge|truncate)\b", re.IGNORECASE),
    "auth_change": re.compile(r"\b(auth|session|token|login|oauth|jwt)\b", re.IGNORECASE),
    "config_change": re.compile(r"\b(config|env|baseurl|base_url|pool|timeout|workers)\b", re.IGNORECASE),
    "dependency_change": re.compile(r"\b(upgrade|bump|update|dependency|deps|package\.json|requirements)\b", re.IGNORECASE),
    "breaking": re.compile(r"\b(breaking|backward[- ]?incompat|v[0-9]+\.[0-9]+\.[0-9]+)\b", re.IGNORECASE),
}


def _run_git(args: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str, str]:
    """Run a git command safely. Returns (returncode, stdout, stderr)."""
    validate_git_args(args)
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,  # never shell=True
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", "git not found in PATH"
    except subprocess.TimeoutExpired:
        return 124, "", "git command timed out"


def _is_git_repo(cwd: Path) -> bool:
    code, _, _ = _run_git(["rev-parse", "--is-inside-work-tree"], cwd)
    return code == 0


def _flag_risks(msg: str, files: list[str]) -> list[str]:
    blob = msg + " " + " ".join(files)
    return [name for name, pat in RISK_PATTERNS.items() if pat.search(blob)]


def scan_git_history(
    workspace: Path,
    since: str = "30 days ago",
    paths: list[str] | None = None,
    max_commits: int = MAX_GIT_COMMITS,
) -> dict[str, Any]:
    """Collect recent commits with risk flags. Returns an evidence-shaped dict.

    Safe to call when there is no git history — it returns ``available=False``
    rather than raising.
    """
    workspace = Path(workspace).resolve()
    max_commits = min(max_commits, MAX_GIT_COMMITS)

    if not _is_git_repo(workspace):
        return {
            "available": False,
            "reason": "not a git repository (or no commits yet)",
            "commits": [],
            "summary": {"total": 0, "high_risk": 0},
        }

    # Use a format that's unambiguous to parse: %x1f field-sep, %x1e record-sep
    fmt = "%H%x1f%h%x1f%an%x1f%ad%x1f%s"
    args = ["log", f"--pretty=format:{fmt}", "--date=short", "--name-only", f"-n{max_commits}", f"--since={since}"]
    if paths:
        args.append("--")
        args.extend(paths)

    code, stdout, stderr = _run_git(args, workspace)
    if code != 0:
        # Empty repo case: git log returns 128 on an empty repo
        return {
            "available": False,
            "reason": stderr.strip() or "git log failed",
            "commits": [],
            "summary": {"total": 0, "high_risk": 0},
        }

    commits = []
    # Split by blank line — each block is: <metadata-line>\n<file1>\n<file2>\n
    for block in stdout.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.splitlines()
        meta = lines[0]
        try:
            full_hash, short_hash, author, date, subject = meta.split("\x1f", 4)
        except ValueError:
            continue
        files = [ln.strip() for ln in lines[1:] if ln.strip()]
        risks = _flag_risks(subject, files)
        commits.append({
            "hash": short_hash,
            "full_hash": full_hash,
            "author": author,
            "date": date,
            "subject": subject,
            "files": files,
            "risk_flags": risks,
            "is_high_risk": bool(risks),
        })

    high_risk = sum(1 for c in commits if c["is_high_risk"])
    return {
        "available": True,
        "since": since,
        "paths_filter": paths,
        "commits": commits,
        "summary": {"total": len(commits), "high_risk": high_risk},
    }


def diff_stat(workspace: Path, ref: str = "HEAD~5") -> dict[str, Any]:
    """Get a summary of changes between ``ref`` and HEAD. Best-effort."""
    workspace = Path(workspace).resolve()
    if not _is_git_repo(workspace):
        return {"available": False}
    code, stdout, _ = _run_git(["diff", "--stat", ref], workspace)
    if code != 0:
        return {"available": False}
    return {"available": True, "ref": ref, "stat": stdout}
