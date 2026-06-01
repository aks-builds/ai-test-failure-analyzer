"""GitHub issue creation via PyGithub. Token is env-only. Dry-run by default."""

from __future__ import annotations

from typing import Any

from .config import github_repository, github_token, settings
from .hypothesis import Hypothesis
from .render.markdown import render_issue_body


def _build_title(hypothesis: Hypothesis) -> str:
    n = len(hypothesis.affected_tests)
    plural = "test" if n == 1 else "tests"
    return f"[Test Failure · {hypothesis.cluster_id}] {hypothesis.title} ({n} {plural})"


def create_issue_from_hypothesis(
    repo: str,
    hypothesis: Hypothesis | None = None,
    explicit_title: str | None = None,
    explicit_body: str | None = None,
    labels: list[str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Create a GitHub issue. Returns a result dict with ``created``, ``url``, ``number``."""
    if not hypothesis and not (explicit_title and explicit_body):
        return {"created": False, "reason": "must provide hypothesis or (title and body)"}

    title = explicit_title or _build_title(hypothesis)  # type: ignore[arg-type]
    body = explicit_body or render_issue_body(hypothesis, run_url=settings().github_run_url)  # type: ignore[arg-type]
    labels = labels or ["test-failure", "auto-triaged"]

    if dry_run:
        return {
            "created": False,
            "dry_run": True,
            "would_create": {
                "repo": repo,
                "title": title,
                "labels": labels,
                "body_preview": body[:500] + ("…" if len(body) > 500 else ""),
                "body_bytes": len(body),
            },
        }

    token = github_token()
    if not token:
        return {
            "created": False,
            "reason": "GITHUB_TOKEN env var not set. Pass dry_run=True to preview without creating.",
        }

    try:
        from github import Github, GithubException  # PyGithub
    except ImportError:
        return {"created": False, "reason": "PyGithub not installed. Run: pip install PyGithub"}

    try:
        gh = Github(token)
        repo_obj = gh.get_repo(repo)
        issue = repo_obj.create_issue(title=title, body=body, labels=labels)
        return {
            "created": True,
            "url": issue.html_url,
            "number": issue.number,
            "repo": repo,
        }
    except GithubException as e:  # type: ignore[name-defined]
        return {
            "created": False,
            "reason": f"GitHub API error: {e.status} {e.data.get('message', '')}",
        }
    except Exception as e:
        return {"created": False, "reason": f"unexpected error: {e}"}


def detect_default_repo() -> str | None:
    """Return ``owner/repo`` from env or by parsing git remote (best-effort)."""
    from_env = github_repository()
    if from_env:
        return from_env

    # Fallback: parse `git remote get-url origin`
    import subprocess

    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, check=False, shell=False,
        )
        if out.returncode != 0:
            return None
        url = out.stdout.strip()
        # git@github.com:owner/repo.git  OR  https://github.com/owner/repo(.git)
        import re

        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(\.git)?$", url)
        if m:
            return m.group(1)
    except Exception:
        return None
    return None
