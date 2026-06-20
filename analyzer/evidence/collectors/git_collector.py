"""GitCollector — wraps the existing git_scan module."""
from __future__ import annotations
from pathlib import Path

from ..bundle import EvidenceBundle
from ..collector import EvidenceCollector
from ..graph import EvidenceNode
from ..git_scan import scan_git_history


class GitCollector(EvidenceCollector):
    """Collects git history evidence. Tier-1 — commit data is root-cause eligible."""

    name = "git"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        return (workspace / ".git").exists()

    @classmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        try:
            legacy = scan_git_history(workspace)
        except Exception:
            return EvidenceBundle.empty("git", "tier1")

        nodes = [
            EvidenceNode(
                id=f"commit:{c['hash']}",
                type="commit",
                ref=c["hash"],
                weight=2.0,
                excerpt=(c.get("subject") or "")[:200],
            )
            for c in legacy.get("commits", [])
        ]
        return EvidenceBundle(
            collector_name="git",
            tier="tier1",
            available=legacy.get("available", False),
            nodes=nodes,
            summary=legacy.get("summary", {}),
            legacy=legacy,
        )
