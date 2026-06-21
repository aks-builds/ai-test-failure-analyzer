"""FlakyHistoryCollector — reads .atfa/history.json for flaky test scoring. Tier-2."""
from __future__ import annotations
import json
from pathlib import Path

from ..bundle import EvidenceBundle
from ..collector import EvidenceCollector
from ..graph import EvidenceNode

_HISTORY_FILE = ".atfa/history.json"
_MAX_RUNS = 50


def _load_history(workspace: Path) -> dict:
    p = workspace / _HISTORY_FILE
    if not p.exists():
        return {"runs": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"runs": []}


def append_run(workspace: Path, run_id: str, timestamp: str, framework: str,
               failures: list) -> None:
    """Write-back: append current run results to history. Called by orchestrator."""
    p = workspace / _HISTORY_FILE
    p.parent.mkdir(exist_ok=True)
    history = _load_history(workspace)
    history.setdefault("runs", [])
    history["runs"].append({
        "run_id": run_id,
        "timestamp": timestamp,
        "framework": framework,
        "failures": [{"id": f.id, "status": f.status} for f in failures],
    })
    history["runs"] = history["runs"][-_MAX_RUNS:]
    p.write_text(json.dumps(history, indent=2), encoding="utf-8")
    # Ensure .atfa/ is gitignored
    gitignore = workspace / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if ".atfa/" not in content:
            gitignore.write_text(content.rstrip() + "\n.atfa/\n", encoding="utf-8")


class FlakyHistoryCollector(EvidenceCollector):
    """Reads local run history for flaky test pattern detection. Tier-2."""
    name = "flaky_history"
    tier = "tier2"

    @classmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        return (workspace / _HISTORY_FILE).exists()

    @classmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        try:
            return cls._collect_safe(workspace)
        except Exception:
            return EvidenceBundle.empty("flaky_history", "tier2")

    @classmethod
    def _collect_safe(cls, workspace: Path) -> EvidenceBundle:
        history = _load_history(workspace)
        runs = history.get("runs", [])
        nodes = [
            EvidenceNode(
                id=f"history:run:{r.get('run_id', i)}",
                type="history",
                ref=r.get("run_id", f"run_{i}"),
                weight=1.0,
                excerpt=f"run {r.get('run_id', '')} — {len(r.get('failures', []))} failures",
            )
            for i, r in enumerate(runs[-10:])
        ]
        return EvidenceBundle(
            collector_name="flaky_history",
            tier="tier2",
            available=bool(runs),
            nodes=nodes,
            summary={"runs": len(runs)},
            legacy={"available": bool(runs), "history": history,
                    "summary": {"runs": len(runs)}},
        )
