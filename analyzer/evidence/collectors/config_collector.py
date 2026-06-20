"""ConfigCollector — wraps the existing config_scan module."""
from __future__ import annotations
import glob
from pathlib import Path

from ..bundle import EvidenceBundle
from ..collector import EvidenceCollector
from ..graph import EvidenceNode
from ..config_scan import scan_config

_CONFIG_GLOBS = [
    ".env",
    "docker-compose.yml",
    "docker-compose.yaml",
    "*.config.js",
    "*.config.ts",
    "*.config.json",
    "config/*.json",
    "config/*.yaml",
]


class ConfigCollector(EvidenceCollector):
    """Collects configuration file evidence. Tier-1 — env/docker values are root-cause eligible."""

    name = "config"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        for pattern in _CONFIG_GLOBS:
            if glob.glob(str(workspace / pattern)):
                return True
        return False

    @classmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        try:
            legacy = scan_config(workspace)
        except Exception:
            return EvidenceBundle.empty("config", "tier1")

        nodes = [
            EvidenceNode(
                id=f"config:{i}",
                type="config",
                ref=f.get("path", ""),
                weight=2.0,
                excerpt=(f.get("excerpt") or "")[:200],
            )
            for i, f in enumerate(legacy.get("files", []))
        ]
        return EvidenceBundle(
            collector_name="config",
            tier="tier1",
            available=legacy.get("available", False),
            nodes=nodes,
            summary=legacy.get("summary", {}),
            legacy=legacy,
        )
