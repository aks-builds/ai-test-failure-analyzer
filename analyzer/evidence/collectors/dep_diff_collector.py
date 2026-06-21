"""DepDiffCollector — detects dependency manifest changes near the test run."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

from ..bundle import EvidenceBundle
from ..collector import EvidenceCollector
from ..graph import EvidenceNode

_MANIFESTS = [
    "package.json", "package-lock.json", "requirements.txt", "pyproject.toml",
    "go.mod", "Gemfile", "Gemfile.lock", "Cargo.toml", "pom.xml", "build.gradle",
]
_DEPTH = 10  # commits back to scan


def _parse_manifest_diff(filename: str, old_text: str, new_text: str) -> list[dict]:
    """Extract added/removed/bumped packages from two manifest snapshots.
    Supports package.json and requirements.txt formats."""
    changes = []
    if filename in ("package.json",):
        try:
            old_deps = {**json.loads(old_text or "{}").get("dependencies", {}),
                        **json.loads(old_text or "{}").get("devDependencies", {})}
            new_deps = {**json.loads(new_text or "{}").get("dependencies", {}),
                        **json.loads(new_text or "{}").get("devDependencies", {})}
        except (json.JSONDecodeError, AttributeError):
            return []
        for pkg in set(old_deps) | set(new_deps):
            old_ver = old_deps.get(pkg)
            new_ver = new_deps.get(pkg)
            if old_ver != new_ver:
                changes.append({
                    "package": pkg,
                    "from": old_ver,
                    "to": new_ver,
                    "file": filename,
                    "change": "removed" if new_ver is None else ("added" if old_ver is None else "bumped"),
                })
    elif filename in ("requirements.txt", "Gemfile"):
        # Line-by-line diff — extract package==version
        import re
        _PKG_RE = re.compile(r"^([A-Za-z0-9_\-\.]+)[=><~!]+(.+)$")
        def _parse_reqs(text):
            pkgs = {}
            for line in (text or "").splitlines():
                m = _PKG_RE.match(line.strip())
                if m:
                    pkgs[m.group(1).lower()] = m.group(2).strip()
            return pkgs
        old_pkgs = _parse_reqs(old_text)
        new_pkgs = _parse_reqs(new_text)
        for pkg in set(old_pkgs) | set(new_pkgs):
            if old_pkgs.get(pkg) != new_pkgs.get(pkg):
                changes.append({
                    "package": pkg,
                    "from": old_pkgs.get(pkg),
                    "to": new_pkgs.get(pkg),
                    "file": filename,
                    "change": "removed" if pkg not in new_pkgs else (
                        "added" if pkg not in old_pkgs else "bumped"),
                })
    return changes


def _git_show(workspace: Path, ref: str, file_path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{file_path}"],
            cwd=str(workspace), capture_output=True, text=True, timeout=10,
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


class DepDiffCollector(EvidenceCollector):
    """Detects dependency manifest changes in the last N commits. Tier-1."""
    name = "dep_diff"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        if not (workspace / ".git").exists():
            return False
        return any((workspace / m).exists() for m in _MANIFESTS)

    @classmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        try:
            return cls._collect_safe(workspace)
        except Exception:
            return EvidenceBundle.empty("dep_diff", "tier1")

    @classmethod
    def _collect_safe(cls, workspace: Path) -> EvidenceBundle:
        nodes: list[EvidenceNode] = []
        all_changes: list[dict] = []

        for manifest in _MANIFESTS:
            if not (workspace / manifest).exists():
                continue
            current_text = (workspace / manifest).read_text(encoding="utf-8", errors="replace")
            old_text = _git_show(workspace, f"HEAD~{_DEPTH}", manifest)
            if old_text is None:
                continue
            changes = _parse_manifest_diff(manifest, old_text, current_text)
            all_changes.extend(changes)
            for i, change in enumerate(changes):
                excerpt = (f"{change['change']}: {change['package']} "
                           f"{change.get('from') or '?'} → {change.get('to') or '?'}")
                nodes.append(EvidenceNode(
                    id=f"dep:{manifest}:{change['package']}:{i}",
                    type="dep_change",
                    ref=manifest,
                    weight=2.0,
                    excerpt=excerpt[:200],
                ))

        return EvidenceBundle(
            collector_name="dep_diff",
            tier="tier1",
            available=bool(nodes),
            nodes=nodes,
            summary={"changes": len(all_changes)},
            legacy={"available": bool(nodes), "dep_changes": all_changes, "summary": {"changes": len(all_changes)}},
        )
