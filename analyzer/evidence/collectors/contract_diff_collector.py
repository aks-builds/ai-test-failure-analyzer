"""ContractDiffCollector — detects breaking changes in committed OpenAPI/Pact specs."""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

from ..bundle import EvidenceBundle
from ..collector import EvidenceCollector
from ..graph import EvidenceNode

_SPEC_GLOBS = ["openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json"]
_PACT_DIRS = ["pact", "pacts"]
_EXTRA_GLOBS = ["*-schema.json", "*.oas.json", "*.pact.json"]


def _find_spec_files(workspace: Path) -> list[Path]:
    found = []
    for pattern in _SPEC_GLOBS:
        found.extend(workspace.rglob(pattern))
    for d in _PACT_DIRS:
        pact_dir = workspace / d
        if pact_dir.is_dir():
            found.extend(pact_dir.rglob("*.json"))
    for pattern in _EXTRA_GLOBS:
        found.extend(workspace.rglob(pattern))
    return found[:10]  # cap to avoid scanning huge repos


def _git_diff_file(workspace: Path, file_path: Path) -> str | None:
    try:
        rel = file_path.relative_to(workspace)
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--", str(rel)],
            cwd=str(workspace), capture_output=True, text=True, timeout=10,
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def _extract_breaking_changes(diff: str) -> list[str]:
    """Heuristically extract breaking changes from an OpenAPI/Pact diff."""
    changes = []
    removed_path_re = re.compile(r"^-\s+/[a-z0-9/_\-{}]+:", re.MULTILINE)
    removed_status_re = re.compile(r"^-\s+['\"]?[245]\d\d['\"]?\s*:", re.MULTILINE)
    removed_required_re = re.compile(r"^-\s+-\s+\w+", re.MULTILINE)
    if removed_path_re.search(diff):
        changes.append("API path removed or renamed")
    if removed_status_re.search(diff):
        changes.append("Response status code removed")
    if removed_required_re.search(diff):
        changes.append("Required field removed from schema")
    return changes


class ContractDiffCollector(EvidenceCollector):
    """Detects breaking API contract changes vs HEAD~1. Tier-1."""
    name = "contract_diff"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        if not (workspace / ".git").exists():
            return False
        return bool(_find_spec_files(workspace))

    @classmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        try:
            return cls._collect_safe(workspace)
        except Exception:
            return EvidenceBundle.empty("contract_diff", "tier1")

    @classmethod
    def _collect_safe(cls, workspace: Path) -> EvidenceBundle:
        nodes: list[EvidenceNode] = []
        all_changes: list[str] = []
        for spec_file in _find_spec_files(workspace):
            diff = _git_diff_file(workspace, spec_file)
            if not diff:
                continue
            breaking = _extract_breaking_changes(diff)
            if not breaking:
                continue
            all_changes.extend(breaking)
            for i, change in enumerate(breaking):
                nodes.append(EvidenceNode(
                    id=f"contract:{spec_file.name}:{i}",
                    type="contract",
                    ref=str(spec_file.relative_to(workspace)),
                    weight=2.0,
                    excerpt=change[:200],
                ))
        return EvidenceBundle(
            collector_name="contract_diff",
            tier="tier1",
            available=bool(nodes),
            nodes=nodes,
            summary={"breaking_changes": len(all_changes)},
            legacy={"available": bool(nodes), "breaking_changes": all_changes,
                    "summary": {"breaking_changes": len(all_changes)}},
        )
