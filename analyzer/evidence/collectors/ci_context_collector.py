"""CIContextCollector — reads CI environment to surface run context. Tier-2."""
from __future__ import annotations
import os
import json
import urllib.request
import urllib.error
from pathlib import Path

from ..bundle import EvidenceBundle
from ..collector import EvidenceCollector
from ..graph import EvidenceNode

_CI_VARS = {
    "github": "GITHUB_ACTIONS",
    "gitlab": "GITLAB_CI",
    "circleci": "CIRCLECI",
    "jenkins": "JENKINS_URL",
}


def _detect_provider() -> str | None:
    if os.environ.get("GITHUB_ACTIONS"):
        return "github"
    if os.environ.get("GITLAB_CI"):
        return "gitlab"
    if os.environ.get("CIRCLECI"):
        return "circleci"
    if os.environ.get("JENKINS_URL"):
        return "jenkins"
    return None


def _read_github_context() -> dict:
    return {
        "provider": "github",
        "sha": os.environ.get("GITHUB_SHA", ""),
        "ref": os.environ.get("GITHUB_REF", ""),
        "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "pr_number": os.environ.get("GITHUB_PR_NUMBER") or os.environ.get("GITHUB_REF", "").split("/")[-2]
            if "/pull/" in os.environ.get("GITHUB_REF", "") else "",
    }


def _read_gitlab_context() -> dict:
    return {
        "provider": "gitlab",
        "sha": os.environ.get("CI_COMMIT_SHA", ""),
        "ref": os.environ.get("CI_COMMIT_REF_NAME", ""),
        "pr_number": os.environ.get("CI_MERGE_REQUEST_IID", ""),
        "pipeline_id": os.environ.get("CI_PIPELINE_ID", ""),
    }


def _fetch_github_pr_files(pr_number: str, token: str) -> list[str]:
    """Fetch list of changed files in a GitHub PR via API. Returns [] on any failure."""
    if not pr_number or not token:
        return []
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return []
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            files = json.loads(resp.read().decode())
            return [f["filename"] for f in files if isinstance(f, dict)]
    except Exception:
        return []


class CIContextCollector(EvidenceCollector):
    """Reads CI env vars to surface run context. Tier-2 — context only."""
    name = "ci_context"
    tier = "tier2"

    @classmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        return _detect_provider() is not None

    @classmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        try:
            return cls._collect_safe(workspace)
        except Exception:
            return EvidenceBundle.empty("ci_context", "tier2")

    @classmethod
    def _collect_safe(cls, workspace: Path) -> EvidenceBundle:
        provider = _detect_provider()
        if not provider:
            return EvidenceBundle.empty("ci_context", "tier2")

        ctx = _read_github_context() if provider == "github" else (
            _read_gitlab_context() if provider == "gitlab" else {"provider": provider}
        )

        changed_files: list[str] = []
        if provider == "github":
            token = os.environ.get("GITHUB_TOKEN", "")
            pr_number = ctx.get("pr_number", "")
            changed_files = _fetch_github_pr_files(pr_number, token)

        nodes: list[EvidenceNode] = []
        nodes.append(EvidenceNode(
            id=f"ci:{provider}:{ctx.get('sha', 'unknown')[:8]}",
            type="ci_context",
            ref=ctx.get("ref", ""),
            weight=1.0,
            excerpt=f"{provider} CI · {ctx.get('ref', '')} · {ctx.get('sha', '')[:8]}",
        ))
        for i, f in enumerate(changed_files[:20]):  # cap at 20
            nodes.append(EvidenceNode(
                id=f"ci:pr_file:{i}",
                type="ci_changed_file",
                ref=f,
                weight=1.0,
                excerpt=f"PR changed: {f}",
            ))

        return EvidenceBundle(
            collector_name="ci_context",
            tier="tier2",
            available=True,
            nodes=nodes,
            summary={"provider": provider, "changed_files": len(changed_files)},
            legacy={"available": True, "provider": provider, "context": ctx,
                    "changed_files": changed_files,
                    "summary": {"provider": provider, "changed_files": len(changed_files)}},
        )
