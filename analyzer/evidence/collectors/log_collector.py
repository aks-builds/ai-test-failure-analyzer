"""LogCollector — wraps the existing log_scan module."""
from __future__ import annotations
import glob
from pathlib import Path

from ..bundle import EvidenceBundle
from ..collector import EvidenceCollector
from ..graph import EvidenceNode
from ..log_scan import scan_logs

_LOG_GLOBS = ["*.log", "logs/*.log", "log/*.log"]


class LogCollector(EvidenceCollector):
    """Collects application log evidence. Tier-1 — ERROR/FATAL lines are root-cause eligible."""

    name = "logs"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        for pattern in _LOG_GLOBS:
            if glob.glob(str(workspace / pattern)):
                return True
        return (workspace / "logs").is_dir()

    @classmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        try:
            legacy = scan_logs(workspace)
        except Exception:
            return EvidenceBundle.empty("logs", "tier1")

        nodes = [
            EvidenceNode(
                id=f"log:{i}",
                type="log_line",
                ref=f"{m.get('file', 'log')}:{m.get('line_no', '')}",
                weight=2.0,
                excerpt=(m.get("text") or "")[:200],
            )
            for i, m in enumerate(legacy.get("matches", []))
        ]
        return EvidenceBundle(
            collector_name="logs",
            tier="tier1",
            available=legacy.get("available", False),
            nodes=nodes,
            summary=legacy.get("summary", {}),
            legacy=legacy,
        )
