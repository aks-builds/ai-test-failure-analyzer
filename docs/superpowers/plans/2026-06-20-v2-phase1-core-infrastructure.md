# v2 Phase 1 — Core Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce ParserRegistry, EvidenceCollector ABC, EvidenceGraph, EvidenceRegistry with parallel ThreadPoolExecutor, and refactor the three existing evidence scanners into collectors — with zero behavior change to the running tool.

**Architecture:** New ABCs and dataclasses are added to a new `collectors/` subpackage and `intelligence/` package. Existing `git_scan.py`, `log_scan.py`, `config_scan.py` are **wrapped** (not deleted) by new collector classes that return `EvidenceBundle` with a `legacy` dict for backward compatibility. The orchestrator's phases 3–5 are merged into Phase 5.5 via `EvidenceRegistry.collect_all()`, which runs all collectors concurrently. The correlator and hypothesis modules are **not changed** in this plan.

**Tech Stack:** Python 3.10+, `concurrent.futures` (stdlib), `abc` (stdlib), `dataclasses` (stdlib), `pathlib` (stdlib). No new dependencies.

## Global Constraints

- Python ≥ 3.10 (uses `match`, `X | Y` union types, `Literal`)
- Zero new runtime dependencies — stdlib only
- All new files must have a module-level docstring
- `EvidenceBundle.legacy` dict must match the exact shape the existing correlator expects
- Existing pytest suite (`pytest tests/analyzer -q`) must pass after every task
- No changes to `analyzer/evidence/correlator.py` or `analyzer/hypothesis.py` in this plan

---

### Task 1: Add three new fields to NormalizedFailure

**Files:**
- Modify: `analyzer/parsers/base.py`
- Test: `tests/analyzer/test_parsers.py` (extend existing)

**Interfaces:**
- Produces: `NormalizedFailure.flakiness_score: float | None`, `NormalizedFailure.flakiness_category: str | None`, `NormalizedFailure.ctrf_extra: dict`

- [ ] **Step 1: Write the failing test**

Add to `tests/analyzer/test_parsers.py`:

```python
def test_normalized_failure_new_fields_default_none():
    """New v2 fields must default to None / empty dict for backward compat."""
    from analyzer.parsers.base import NormalizedFailure
    f = NormalizedFailure(
        id="abc", framework="pytest", suite="s", title="t", file="f.py"
    )
    assert f.flakiness_score is None
    assert f.flakiness_category is None
    assert f.ctrf_extra == {}


def test_normalized_failure_new_fields_set():
    from analyzer.parsers.base import NormalizedFailure
    f = NormalizedFailure(
        id="abc", framework="pytest", suite="s", title="t", file="f.py",
        flakiness_score=0.75,
        flakiness_category="ID",
        ctrf_extra={"foo": "bar"},
    )
    assert f.flakiness_score == 0.75
    assert f.flakiness_category == "ID"
    assert f.ctrf_extra == {"foo": "bar"}
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/analyzer/test_parsers.py::test_normalized_failure_new_fields_default_none -v
```
Expected: `FAILED` — `TypeError: __init__() got an unexpected keyword argument 'flakiness_score'`

- [ ] **Step 3: Add the three fields to NormalizedFailure in `analyzer/parsers/base.py`**

Find the `NormalizedFailure` dataclass (currently ends at `raw: dict = field(default_factory=dict)`). Add after `raw`:

```python
    # v2 intelligence fields — backward compatible, all default to None / empty
    flakiness_score: float | None = None
    flakiness_category: str | None = None
    ctrf_extra: dict = field(default_factory=dict)
```

- [ ] **Step 4: Run tests**

```
pytest tests/analyzer/test_parsers.py -v
```
Expected: all pass.

- [ ] **Step 5: Run full suite to confirm no regression**

```
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add analyzer/parsers/base.py tests/analyzer/test_parsers.py
git commit -m "feat(v2): add flakiness_score, flakiness_category, ctrf_extra to NormalizedFailure"
```

---

### Task 2: EvidenceNode, EvidenceEdge, EvidenceBundle dataclasses

**Files:**
- Create: `analyzer/evidence/graph.py`
- Create: `analyzer/evidence/bundle.py`
- Create: `tests/analyzer/test_evidence_graph.py`

**Interfaces:**
- Produces:
  - `EvidenceNode(id, type, ref, weight, excerpt)`
  - `EvidenceEdge(src, dst, relation, weight)`
  - `EvidenceBundle(collector_name, tier, available, nodes, summary, legacy)` + `EvidenceBundle.empty(name, tier)`
  - `EvidenceGraph` class with `add_node`, `add_edge`, `strongest_chain`, `total_weight`, `nodes_for_cluster`

- [ ] **Step 1: Write the failing tests**

Create `tests/analyzer/test_evidence_graph.py`:

```python
"""Tests for EvidenceGraph, EvidenceNode, EvidenceEdge, EvidenceBundle."""
import pytest
from analyzer.evidence.graph import EvidenceEdge, EvidenceGraph, EvidenceNode
from analyzer.evidence.bundle import EvidenceBundle


def _node(id_, type_="commit", weight=2.0):
    return EvidenceNode(id=id_, type=type_, ref=f"ref:{id_}", weight=weight, excerpt="x")


def test_evidence_graph_add_and_retrieve_node():
    g = EvidenceGraph()
    n = _node("c1")
    g.add_node(n)
    assert "c1" in g.nodes
    assert g.nodes["c1"] is n


def test_evidence_graph_add_edge():
    g = EvidenceGraph()
    g.add_node(_node("f1", "failure"))
    g.add_node(_node("c1", "commit"))
    g.add_edge(EvidenceEdge(src="f1", dst="c1", relation="caused_by", weight=2.0))
    assert len(g.edges) == 1


def test_total_weight_sums_outgoing_edges():
    g = EvidenceGraph()
    g.add_node(_node("f1", "failure"))
    g.add_node(_node("c1"))
    g.add_node(_node("l1", "log_line", weight=1.0))
    g.add_edge(EvidenceEdge(src="f1", dst="c1", relation="caused_by", weight=2.0))
    g.add_edge(EvidenceEdge(src="f1", dst="l1", relation="related_to", weight=1.0))
    assert g.total_weight("f1") == 3.0


def test_total_weight_missing_node_returns_zero():
    g = EvidenceGraph()
    assert g.total_weight("nonexistent") == 0.0


def test_strongest_chain_returns_path():
    g = EvidenceGraph()
    g.add_node(_node("f1", "failure", weight=0.0))
    g.add_node(_node("c1", "commit", weight=2.0))
    g.add_edge(EvidenceEdge(src="f1", dst="c1", relation="caused_by", weight=2.0))
    chain = g.strongest_chain("f1")
    assert len(chain) >= 1
    assert any(n.id == "c1" for n in chain)


def test_strongest_chain_missing_node_returns_empty():
    g = EvidenceGraph()
    assert g.strongest_chain("none") == []


def test_nodes_for_cluster():
    g = EvidenceGraph()
    g.add_node(_node("f1", "failure"))
    g.add_node(_node("f2", "failure"))
    g.add_node(_node("c1", "commit"))
    g.add_node(_node("c2", "commit"))
    g.add_edge(EvidenceEdge(src="f1", dst="c1", relation="caused_by", weight=2.0))
    g.add_edge(EvidenceEdge(src="f2", dst="c2", relation="caused_by", weight=2.0))
    result = g.nodes_for_cluster(["f1"])
    ids = {n.id for n in result}
    assert "c1" in ids
    assert "c2" not in ids


def test_evidence_bundle_empty():
    b = EvidenceBundle.empty("git", "tier1")
    assert b.available is False
    assert b.nodes == []
    assert b.legacy == {"available": False, "summary": {}}


def test_evidence_bundle_populated():
    n = _node("c1")
    b = EvidenceBundle(
        collector_name="git", tier="tier1", available=True,
        nodes=[n], summary={"commits": 1}, legacy={"available": True}
    )
    assert b.available is True
    assert len(b.nodes) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/analyzer/test_evidence_graph.py -v
```
Expected: `ERROR` — `ModuleNotFoundError: No module named 'analyzer.evidence.graph'`

- [ ] **Step 3: Create `analyzer/evidence/bundle.py`**

```python
"""EvidenceBundle — what an EvidenceCollector returns."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .graph import EvidenceNode


@dataclass
class EvidenceBundle:
    """Result of one EvidenceCollector.collect() call."""
    collector_name: str
    tier: Literal["tier1", "tier2"]
    available: bool
    nodes: list["EvidenceNode"] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    legacy: dict = field(default_factory=dict)

    @classmethod
    def empty(cls, name: str, tier: Literal["tier1", "tier2"] = "tier1") -> "EvidenceBundle":
        return cls(
            collector_name=name,
            tier=tier,
            available=False,
            legacy={"available": False, "summary": {}},
        )
```

- [ ] **Step 4: Create `analyzer/evidence/graph.py`**

```python
"""EvidenceGraph — pure Python adjacency list for evidence correlation."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class EvidenceNode:
    id: str
    type: str    # "failure"|"commit"|"log_line"|"dep_change"|"span"|"config"|"contract"
    ref: str     # file:line, commit hash, log line, etc.
    weight: float  # tier1=2.0, tier2=1.0, noise=0.0
    excerpt: str


@dataclass
class EvidenceEdge:
    src: str
    dst: str
    relation: str  # "caused_by"|"co_occurs_with"|"related_to"|"contradicts"
    weight: float


class EvidenceGraph:
    """Weighted directed graph of evidence nodes. Pure Python — no external deps."""

    def __init__(self) -> None:
        self.nodes: dict[str, EvidenceNode] = {}
        self.edges: list[EvidenceEdge] = []

    def add_node(self, node: EvidenceNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: EvidenceEdge) -> None:
        self.edges.append(edge)

    def total_weight(self, failure_id: str) -> float:
        """Sum of weights on all outgoing edges from a node."""
        return sum(e.weight for e in self.edges if e.src == failure_id)

    def strongest_chain(self, failure_id: str) -> list[EvidenceNode]:
        """BFS from failure_id; returns the highest-weight path to any evidence node."""
        if failure_id not in self.nodes:
            return []
        adj: dict[str, list[tuple[str, float]]] = {}
        for e in self.edges:
            adj.setdefault(e.src, []).append((e.dst, e.weight))

        best: dict[str, float] = {failure_id: 0.0}
        prev: dict[str, str | None] = {failure_id: None}
        queue = [failure_id]
        while queue:
            curr = queue.pop(0)
            for neighbor, w in adj.get(curr, []):
                new_w = best[curr] + w
                if neighbor not in best or new_w > best[neighbor]:
                    best[neighbor] = new_w
                    prev[neighbor] = curr
                    queue.append(neighbor)

        candidates = [nid for nid in best if nid != failure_id and nid in self.nodes]
        if not candidates:
            return []
        terminal = max(candidates, key=lambda nid: best[nid])

        path: list[EvidenceNode] = []
        curr = terminal
        while curr is not None:
            if curr in self.nodes:
                path.append(self.nodes[curr])
            curr = prev.get(curr)
        path.reverse()
        return path

    def nodes_for_cluster(self, failure_ids: list[str]) -> list[EvidenceNode]:
        """All evidence nodes linked from any failure in the cluster."""
        linked: set[str] = set()
        fid_set = set(failure_ids)
        for e in self.edges:
            if e.src in fid_set:
                linked.add(e.dst)
        return [self.nodes[nid] for nid in linked if nid in self.nodes]
```

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_evidence_graph.py -v
```
Expected: all pass.

- [ ] **Step 6: Run full suite**

```
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add analyzer/evidence/graph.py analyzer/evidence/bundle.py tests/analyzer/test_evidence_graph.py
git commit -m "feat(v2): add EvidenceNode, EvidenceEdge, EvidenceGraph, EvidenceBundle dataclasses"
```

---

### Task 3: EvidenceCollector ABC + EvidenceRegistry (no parallel yet)

**Files:**
- Create: `analyzer/evidence/collector.py`
- Create: `analyzer/evidence/registry.py`
- Create: `tests/analyzer/test_evidence_registry.py`

**Interfaces:**
- Consumes: `EvidenceBundle` from `analyzer.evidence.bundle`, `WorkspaceProfile` from `analyzer.workspace_scanner`
- Produces:
  - `EvidenceCollector` ABC with `name: ClassVar[str]`, `tier: ClassVar[str]`, `is_available(workspace, profile) -> bool`, `collect(workspace, profile) -> EvidenceBundle`
  - `EvidenceRegistry` with `register(collector_cls)`, `collect_all(workspace, profile, timeout) -> dict[str, EvidenceBundle]`

- [ ] **Step 1: Write failing tests**

Create `tests/analyzer/test_evidence_registry.py`:

```python
"""Tests for EvidenceCollector ABC and EvidenceRegistry."""
from pathlib import Path
import pytest
from analyzer.evidence.collector import EvidenceCollector
from analyzer.evidence.registry import EvidenceRegistry
from analyzer.evidence.bundle import EvidenceBundle


class _AlwaysAvailableCollector(EvidenceCollector):
    name = "always"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace, profile):
        return True

    @classmethod
    def collect(cls, workspace, profile):
        return EvidenceBundle(
            collector_name="always", tier="tier1", available=True,
            summary={"ok": True}, legacy={"available": True}
        )


class _NeverAvailableCollector(EvidenceCollector):
    name = "never"
    tier = "tier2"

    @classmethod
    def is_available(cls, workspace, profile):
        return False

    @classmethod
    def collect(cls, workspace, profile):
        raise AssertionError("should never be called")


class _FailingCollector(EvidenceCollector):
    name = "failing"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace, profile):
        return True

    @classmethod
    def collect(cls, workspace, profile):
        raise RuntimeError("boom")


def _fresh_registry():
    """Return a registry with no registered collectors."""
    r = EvidenceRegistry()
    r._collectors = []
    return r


def test_registry_collects_available(tmp_path):
    r = _fresh_registry()
    r.register(_AlwaysAvailableCollector)
    results = r.collect_all(tmp_path, profile=None, timeout=10)
    assert "always" in results
    assert results["always"].available is True


def test_registry_skips_unavailable(tmp_path):
    r = _fresh_registry()
    r.register(_NeverAvailableCollector)
    results = r.collect_all(tmp_path, profile=None, timeout=10)
    assert "never" in results
    assert results["never"].available is False


def test_registry_handles_collector_exception(tmp_path):
    r = _fresh_registry()
    r.register(_FailingCollector)
    # should not raise — returns empty bundle
    results = r.collect_all(tmp_path, profile=None, timeout=10)
    assert "failing" in results
    assert results["failing"].available is False


def test_collector_abstract_cannot_be_instantiated():
    with pytest.raises(TypeError):
        EvidenceCollector()
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_evidence_registry.py -v
```
Expected: `ERROR` — `ModuleNotFoundError: No module named 'analyzer.evidence.collector'`

- [ ] **Step 3: Create `analyzer/evidence/collector.py`**

```python
"""EvidenceCollector — abstract base class all evidence collectors implement."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Literal

from .bundle import EvidenceBundle


class EvidenceCollector(ABC):
    """Collect one evidence source from a workspace."""
    name: ClassVar[str]
    tier: ClassVar[Literal["tier1", "tier2"]]

    @classmethod
    @abstractmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        """Return True if this collector can run in this workspace.
        Fast — only existence checks, no subprocess calls."""

    @classmethod
    @abstractmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        """Collect evidence. Must never raise — catch all exceptions internally."""
```

- [ ] **Step 4: Create `analyzer/evidence/registry.py`**

```python
"""EvidenceRegistry — discovers and runs all registered collectors."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

from .bundle import EvidenceBundle
from .collector import EvidenceCollector


class EvidenceRegistry:
    """Registry of all EvidenceCollectors. Runs available ones concurrently."""

    def __init__(self) -> None:
        self._collectors: list[type[EvidenceCollector]] = []

    def register(self, collector: type[EvidenceCollector]) -> None:
        self._collectors.append(collector)

    def collect_all(
        self,
        workspace: Path,
        profile,
        timeout: int = 30,
        emit=None,
    ) -> dict[str, EvidenceBundle]:
        """Run all available collectors concurrently.

        Args:
            workspace: Repo root path.
            profile: WorkspaceProfile (may be None in tests).
            timeout: Per-collector timeout in seconds.
            emit: Optional progress callback — called with phase progress dicts.

        Returns:
            Mapping of collector_name → EvidenceBundle.
            Unavailable or failed collectors return EvidenceBundle.empty().
        """
        results: dict[str, EvidenceBundle] = {}
        available = [c for c in self._collectors if c.is_available(workspace, profile)]
        unavailable = [c for c in self._collectors if not c.is_available(workspace, profile)]

        for c in unavailable:
            results[c.name] = EvidenceBundle.empty(c.name, c.tier)
            if emit:
                emit({"collector": c.name, "status": "skipped"})

        if not available:
            return results

        with ThreadPoolExecutor(max_workers=min(len(available), 6)) as pool:
            futures = {pool.submit(c.collect, workspace, profile): c for c in available}
            for future, collector in futures.items():
                try:
                    results[collector.name] = future.result(timeout=timeout)
                    if emit:
                        emit({"collector": collector.name, "status": "completed"})
                except FutureTimeout:
                    results[collector.name] = EvidenceBundle.empty(collector.name, collector.tier)
                    if emit:
                        emit({"collector": collector.name, "status": "timeout"})
                except Exception as exc:
                    results[collector.name] = EvidenceBundle.empty(collector.name, collector.tier)
                    if emit:
                        emit({"collector": collector.name, "status": "error", "error": str(exc)})

        return results
```

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_evidence_registry.py -v
```
Expected: all pass.

- [ ] **Step 6: Run full suite**

```
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add analyzer/evidence/collector.py analyzer/evidence/registry.py tests/analyzer/test_evidence_registry.py
git commit -m "feat(v2): add EvidenceCollector ABC and EvidenceRegistry with parallel ThreadPoolExecutor"
```

---

### Task 4: Refactor GitCollector (wrap existing git_scan.py)

**Files:**
- Create: `analyzer/evidence/collectors/__init__.py`
- Create: `analyzer/evidence/collectors/git_collector.py`
- Test: `tests/analyzer/test_evidence_registry.py` (extend)

**Interfaces:**
- Consumes: `scan_git_history` from `analyzer.evidence.git_scan` (existing, unchanged)
- Produces: `GitCollector` — `name="git"`, `tier="tier1"`, wraps `scan_git_history`, returns `EvidenceBundle` with `legacy=<git dict>`

- [ ] **Step 1: Write the failing test**

Add to `tests/analyzer/test_evidence_registry.py`:

```python
def test_git_collector_wraps_legacy_output(tmp_path):
    """GitCollector must return an EvidenceBundle whose .legacy matches
    the exact shape scan_git_history() returns."""
    from analyzer.evidence.collectors.git_collector import GitCollector
    # tmp_path has no .git — collector should be unavailable
    assert GitCollector.is_available(tmp_path, profile=None) is False
    bundle = GitCollector.collect(tmp_path, profile=None)
    assert bundle.available is False
    assert "available" in bundle.legacy


def test_git_collector_available_in_real_repo():
    """Collector is available when .git/ exists (this test runs inside the repo)."""
    from pathlib import Path
    from analyzer.evidence.collectors.git_collector import GitCollector
    repo_root = Path(__file__).parent.parent.parent  # ai-test-failure-analyzer/
    if not (repo_root / ".git").exists():
        pytest.skip("not inside a git repo")
    assert GitCollector.is_available(repo_root, profile=None) is True
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_evidence_registry.py::test_git_collector_wraps_legacy_output -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/evidence/collectors/__init__.py`**

```python
"""Built-in evidence collectors — all ship with the package."""
```

- [ ] **Step 4: Create `analyzer/evidence/collectors/git_collector.py`**

```python
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
        except Exception as exc:
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
```

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_evidence_registry.py -v
```
Expected: all pass.

- [ ] **Step 6: Run full suite**

```
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add analyzer/evidence/collectors/__init__.py analyzer/evidence/collectors/git_collector.py tests/analyzer/test_evidence_registry.py
git commit -m "feat(v2): add GitCollector wrapping existing scan_git_history"
```

---

### Task 5: LogCollector and ConfigCollector

**Files:**
- Create: `analyzer/evidence/collectors/log_collector.py`
- Create: `analyzer/evidence/collectors/config_collector.py`
- Test: `tests/analyzer/test_evidence_registry.py` (extend)

**Interfaces:**
- Consumes: `scan_logs` from `analyzer.evidence.log_scan`, `scan_config` from `analyzer.evidence.config_scan`
- Produces: `LogCollector` (`name="logs"`, `tier="tier1"`), `ConfigCollector` (`name="config"`, `tier="tier1"`)

- [ ] **Step 1: Write failing tests**

Add to `tests/analyzer/test_evidence_registry.py`:

```python
def test_log_collector_unavailable_in_empty_dir(tmp_path):
    from analyzer.evidence.collectors.log_collector import LogCollector
    assert LogCollector.is_available(tmp_path, profile=None) is False
    bundle = LogCollector.collect(tmp_path, profile=None)
    assert bundle.available is False
    assert "available" in bundle.legacy


def test_log_collector_available_when_log_file_exists(tmp_path):
    from analyzer.evidence.collectors.log_collector import LogCollector
    (tmp_path / "app.log").write_text("ERROR something failed\n")
    assert LogCollector.is_available(tmp_path, profile=None) is True


def test_config_collector_unavailable_in_empty_dir(tmp_path):
    from analyzer.evidence.collectors.config_collector import ConfigCollector
    assert ConfigCollector.is_available(tmp_path, profile=None) is False
    bundle = ConfigCollector.collect(tmp_path, profile=None)
    assert bundle.available is False


def test_config_collector_available_when_env_exists(tmp_path):
    from analyzer.evidence.collectors.config_collector import ConfigCollector
    (tmp_path / ".env").write_text("DATABASE_URL=postgres://...\n")
    assert ConfigCollector.is_available(tmp_path, profile=None) is True
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_evidence_registry.py::test_log_collector_unavailable_in_empty_dir -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/evidence/collectors/log_collector.py`**

```python
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
                ref=f"{m.get('file', 'log')}:{m.get('line', '')}",
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
```

- [ ] **Step 4: Create `analyzer/evidence/collectors/config_collector.py`**

```python
"""ConfigCollector — wraps the existing config_scan module."""
from __future__ import annotations
import glob
from pathlib import Path

from ..bundle import EvidenceBundle
from ..collector import EvidenceCollector
from ..graph import EvidenceNode
from ..config_scan import scan_config

_CONFIG_GLOBS = [".env", "docker-compose.yml", "docker-compose.yaml", "*.config.js",
                 "*.config.ts", "*.config.json", "config/*.json", "config/*.yaml"]


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
                excerpt=str(f.get("vars", {}))[:200],
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
```

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_evidence_registry.py -v
```
Expected: all pass.

- [ ] **Step 6: Run full suite**

```
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add analyzer/evidence/collectors/log_collector.py analyzer/evidence/collectors/config_collector.py tests/analyzer/test_evidence_registry.py
git commit -m "feat(v2): add LogCollector and ConfigCollector wrapping existing scan modules"
```

---

### Task 6: Wire EvidenceRegistry into orchestrator (Phase 5.5)

**Files:**
- Modify: `analyzer/orchestrator.py`
- Modify: `analyzer/evidence/__init__.py`

**Interfaces:**
- Consumes: `EvidenceRegistry`, `GitCollector`, `LogCollector`, `ConfigCollector`
- Produces: Orchestrator uses `EvidenceRegistry.collect_all()` for phases 3–5; legacy dicts extracted from bundles for correlator backward compat. `AnalysisResult.phase_timings: dict[str, float]` added.

- [ ] **Step 1: Write the failing test**

Add to `tests/analyzer/test_orchestrator.py` (check if it exists; if so extend it):

```python
def test_orchestrator_phase_timings_present(tmp_path):
    """AnalysisResult must have phase_timings dict after v2 orchestrator."""
    from analyzer.orchestrator import AnalysisResult
    import dataclasses
    fields = {f.name for f in dataclasses.fields(AnalysisResult)}
    assert "phase_timings" in fields
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_orchestrator.py::test_orchestrator_phase_timings_present -v
```
Expected: `FAILED` — `phase_timings` not in fields.

- [ ] **Step 3: Update `analyzer/evidence/__init__.py` to export new types**

Open `analyzer/evidence/__init__.py`. Add after existing exports:

```python
from .bundle import EvidenceBundle
from .collector import EvidenceCollector
from .graph import EvidenceEdge, EvidenceGraph, EvidenceNode
from .registry import EvidenceRegistry
from .collectors.git_collector import GitCollector
from .collectors.log_collector import LogCollector
from .collectors.config_collector import ConfigCollector

# Module-level shared registry — pre-registered with the three core collectors
_REGISTRY = EvidenceRegistry()
_REGISTRY.register(GitCollector)
_REGISTRY.register(LogCollector)
_REGISTRY.register(ConfigCollector)
```

- [ ] **Step 4: Add `phase_timings` to `AnalysisResult` in `analyzer/orchestrator.py`**

Find the `AnalysisResult` dataclass. Add:

```python
    phase_timings: dict = field(default_factory=dict)
```

Import `field` from dataclasses if not already imported (check top of file — it imports `dataclass` but may not import `field`).

- [ ] **Step 5: Replace sequential phases 3-5 with Phase 5.5 in `analyze()`**

In `analyzer/orchestrator.py`, find the section between Phase 2 emit and Phase 6 emit. Replace the three sequential blocks (Phase 3 git, Phase 4 logs, Phase 5 config) with:

```python
    # ── Phase 5.5: Collect evidence (parallel) ─────────────────────────────
    from .evidence import _REGISTRY
    import time as _time
    emit({"phase": "5.5", "name": "Collect evidence", "status": "started"})
    _t55 = _time.monotonic()
    bundles = _REGISTRY.collect_all(workspace, profile, timeout=30, emit=emit)
    phase_timings["5.5_collect_evidence"] = _time.monotonic() - _t55

    # Extract legacy dicts for backward compat with correlator (unchanged in Phase 1)
    git   = bundles.get("git",    type("_", (), {"legacy": {"available": False, "commits": [], "summary": {}}})()).legacy
    logs  = bundles.get("logs",   type("_", (), {"legacy": {"available": False, "matches": [], "summary": {}}})()).legacy
    config = bundles.get("config", type("_", (), {"legacy": {"available": False, "files": [], "summary": {}}})()).legacy

    # Compat: retrieve legacy from EvidenceBundle properly
    def _legacy(name, fallback):
        b = bundles.get(name)
        return b.legacy if (b and b.legacy) else fallback

    git    = _legacy("git",    {"available": False, "commits": [], "summary": {}})
    logs   = _legacy("logs",   {"available": False, "matches": [], "summary": {}})
    config = _legacy("config", {"available": False, "files":   [], "summary": {}})

    active = [name for name, b in bundles.items() if b.available]
    emit({
        "phase": "5.5", "name": "Collect evidence", "status": "completed",
        "data": {"active_collectors": active, "elapsed_ms": int(phase_timings["5.5_collect_evidence"] * 1000)},
    })
```

Also add `phase_timings: dict = {}` at the top of `analyze()` (right after `start = time.monotonic()`), and pass it into `AnalysisResult(...)` at the bottom.

Also remove or comment out the now-redundant individual Phase 3/4/5 emit blocks (they are replaced by 5.5).

- [ ] **Step 6: Run tests**

```
pytest tests/analyzer/test_orchestrator.py -v
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add analyzer/orchestrator.py analyzer/evidence/__init__.py
git commit -m "feat(v2): wire EvidenceRegistry into orchestrator as Phase 5.5 parallel collection"
```

---

### Task 7: ParserRegistry

**Files:**
- Create: `analyzer/parsers/registry.py`
- Modify: `analyzer/parsers/__init__.py`
- Test: `tests/analyzer/test_parsers.py` (extend)

**Interfaces:**
- Produces: `ParserRegistry` class with `register(parser_cls, aliases=[])`, `detect(path) -> type[Parser] | None`, `parse(path, framework) -> tuple[str, list[NormalizedFailure]]`

- [ ] **Step 1: Write failing test**

Add to `tests/analyzer/test_parsers.py`:

```python
def test_parser_registry_detect_playwright(tmp_path):
    """Registry detect() must return PlaywrightJsonParser for a playwright file."""
    import json
    from analyzer.parsers.registry import ParserRegistry
    from analyzer.parsers.playwright_json import PlaywrightJsonParser

    report = {"config": {}, "suites": [], "stats": {}}
    p = tmp_path / "results.json"
    p.write_text(json.dumps(report))
    result = ParserRegistry.detect(p)
    assert result is PlaywrightJsonParser


def test_parser_registry_unknown_returns_none(tmp_path):
    from analyzer.parsers.registry import ParserRegistry
    p = tmp_path / "unknown.json"
    p.write_text('{"foo": "bar"}')
    result = ParserRegistry.detect(p)
    assert result is None
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_parsers.py::test_parser_registry_detect_playwright -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/parsers/registry.py`**

```python
"""ParserRegistry — internal registry for all framework parsers."""
from __future__ import annotations
import os
from pathlib import Path
from typing import ClassVar

from .base import NormalizedFailure, Parser


class ParserRegistry:
    """Registry of all Parser subclasses. Order = detection priority (most specific first)."""
    _parsers: ClassVar[list[type[Parser]]] = []
    _frameworks: ClassVar[dict[str, type[Parser]]] = {}

    @classmethod
    def register(cls, parser: type[Parser], aliases: list[str] | None = None) -> None:
        cls._parsers.append(parser)
        cls._frameworks[parser.framework] = parser
        for alias in (aliases or []):
            cls._frameworks[alias.lower()] = parser

    @classmethod
    def detect(cls, path: Path) -> type[Parser] | None:
        safe = os.path.realpath(str(path))
        safe_parent = os.path.realpath(os.path.dirname(safe))
        if not (safe.startswith(safe_parent + os.sep) or safe == safe_parent):
            return None
        if not os.path.isfile(safe):
            return None
        try:
            with open(safe, "rb") as f:
                sample = f.read(4096)
        except OSError:
            return None
        for parser in cls._parsers:
            try:
                if parser.can_parse(sample):
                    return parser
            except Exception:
                continue
        return None

    @classmethod
    def parse(cls, path: Path, framework: str = "auto") -> tuple[str, list[NormalizedFailure]]:
        if framework != "auto":
            pcls = cls._frameworks.get(framework.lower())
            if pcls is None:
                raise ValueError(f"unknown framework: {framework!r}")
            return pcls.framework, pcls.parse(path)
        pcls = cls.detect(path)
        if pcls is None:
            raise ValueError(
                f"could not detect framework for {path}. "
                f"Pass framework= explicitly. Known: {sorted(cls._frameworks)}"
            )
        return pcls.framework, pcls.parse(path)
```

- [ ] **Step 4: Register existing parsers in `analyzer/parsers/__init__.py`**

Open `analyzer/parsers/__init__.py`. After the existing `PARSERS` list definition, add:

```python
from .registry import ParserRegistry as _Registry

# Register all existing parsers in detection-priority order
_Registry.register(PlaywrightJsonParser)
_Registry.register(NewmanJsonParser,  aliases=["newman"])
_Registry.register(K6JsonParser,      aliases=["k6"])
_Registry.register(JestJsonParser,    aliases=["jest", "vitest"])
_Registry.register(CypressJsonParser, aliases=["cypress", "webdriverio", "wdio"])
_Registry.register(PytestJUnitParser, aliases=["pytest"])
_Registry.register(JUnitXmlParser,    aliases=["junit", "rest-assured", "karate", "insomnia"])
```

Also export `ParserRegistry` from `__all__`.

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_parsers.py -v
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add analyzer/parsers/registry.py analyzer/parsers/__init__.py tests/analyzer/test_parsers.py
git commit -m "feat(v2): add ParserRegistry with register/detect/parse, wire existing 7 parsers"
```

---

### Task 8: Integration smoke test — no behavior regression

**Files:**
- Test: `tests/analyzer/test_orchestrator.py` (extend or create)

This task verifies the full end-to-end analysis still produces the same output for existing fixtures after all Phase 1 changes.

- [ ] **Step 1: Write the smoke test**

Add to `tests/analyzer/test_orchestrator.py`:

```python
def test_orchestrator_end_to_end_playwright(tmp_path):
    """Full analysis on playwright fixture must produce hypotheses and phase_timings."""
    import shutil, json
    from pathlib import Path
    from analyzer.orchestrator import analyze

    fixture = Path(__file__).parent / "fixtures" / "playwright_results.json"
    dest = tmp_path / "results.json"
    shutil.copy(fixture, dest)

    result = analyze(str(dest), workspace=str(tmp_path))

    assert result.framework == "playwright"
    assert isinstance(result.hypotheses, list)
    assert isinstance(result.report_markdown, str)
    assert len(result.report_markdown) > 0
    assert isinstance(result.phase_timings, dict)
    # Phase 5.5 timing must be present
    assert any("collect" in k for k in result.phase_timings)


def test_orchestrator_end_to_end_pytest_junit(tmp_path):
    """Full analysis on pytest JUnit fixture must succeed."""
    import shutil
    from pathlib import Path
    from analyzer.orchestrator import analyze

    fixture = Path(__file__).parent / "fixtures" / "pytest_junit.xml"
    dest = tmp_path / "results.xml"
    shutil.copy(fixture, dest)

    result = analyze(str(dest), workspace=str(tmp_path))
    assert result.framework in ("pytest", "junit")
    assert isinstance(result.report_markdown, str)
```

- [ ] **Step 2: Run smoke tests**

```
pytest tests/analyzer/test_orchestrator.py -v
```
Expected: all pass.

- [ ] **Step 3: Run full suite one final time**

```
pytest tests/analyzer -q
npm test
```
Expected: all pass.

- [ ] **Step 4: Commit**

```
git add tests/analyzer/test_orchestrator.py
git commit -m "test(v2): add orchestrator smoke tests verifying phase_timings and no regression"
```

---

## Phase 1 Complete

At this point:
- `NormalizedFailure` has 3 new backward-compatible fields
- `EvidenceGraph`, `EvidenceBundle`, `EvidenceCollector`, `EvidenceRegistry` all exist
- `GitCollector`, `LogCollector`, `ConfigCollector` wrap existing scan functions
- Orchestrator uses parallel collection (Phase 5.5)
- `ParserRegistry` is wired with all 7 existing parsers
- All existing tests pass — zero behavior change

**Next:** Phase 2 — Parser Ecosystem (17 new parsers)
