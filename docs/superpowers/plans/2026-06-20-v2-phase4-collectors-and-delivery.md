# v2 Phase 4 — New Collectors + Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 new evidence collectors (DepDiff, ContractDiff, CIContext, OTel, FlakyHistory), CTRF output format, result caching, watch mode, optional LLM enrichment, phase timings in TUI, language-specific remediation, GitHub App, and Docker image.

**Architecture:** Each collector is a self-contained file in `analyzer/evidence/collectors/`. CTRF output is a new render module. Caching uses SHA1 + JSON via stdlib. The GitHub App is a minimal Node.js file in `bin/github-app/`. Docker is a two-stage `Dockerfile`.

**Tech Stack:** Python stdlib (`subprocess`, `urllib.request`, `hashlib`, `json`, `os`, `time`). Node.js for GitHub App (no npm deps beyond `@octokit/webhooks`). Zero new Python runtime dependencies.

## Global Constraints

- Python ≥ 3.10, zero new Python runtime dependencies
- Every collector's `collect()` must catch all exceptions — never raise
- Cache files stored at `.atfa/cache/<sha1>.json`, expire after 24h
- `--enrich` flag is strictly opt-in — no LLM call without it
- Secrets (API keys, tokens, passwords) must be redacted in all report output
- `pytest tests/analyzer -q` and `npm test` must pass after every task

---

### Task 1: DepDiffCollector

**Files:**
- Create: `analyzer/evidence/collectors/dep_diff_collector.py`
- Create: `tests/analyzer/test_dep_diff_collector.py`

**Interfaces:**
- Produces: `DepDiffCollector` — `name="dep_diff"`, `tier="tier1"`, available when `.git` + any manifest exists, emits `EvidenceNode` per changed package

- [ ] **Step 1: Write failing tests**

Create `tests/analyzer/test_dep_diff_collector.py`:

```python
"""Tests for DepDiffCollector."""
import json
import pytest
from pathlib import Path


def test_dep_diff_unavailable_without_git(tmp_path):
    from analyzer.evidence.collectors.dep_diff_collector import DepDiffCollector
    (tmp_path / "package.json").write_text('{"dependencies": {}}')
    assert DepDiffCollector.is_available(tmp_path, profile=None) is False


def test_dep_diff_unavailable_without_manifest(tmp_path):
    from analyzer.evidence.collectors.dep_diff_collector import DepDiffCollector
    (tmp_path / ".git").mkdir()
    assert DepDiffCollector.is_available(tmp_path, profile=None) is False


def test_dep_diff_available_with_git_and_manifest(tmp_path):
    from analyzer.evidence.collectors.dep_diff_collector import DepDiffCollector
    (tmp_path / ".git").mkdir()
    (tmp_path / "package.json").write_text('{"dependencies": {}}')
    assert DepDiffCollector.is_available(tmp_path, profile=None) is True


def test_dep_diff_collect_returns_bundle_on_no_git(tmp_path):
    """collect() must return empty bundle (not raise) when git fails."""
    from analyzer.evidence.collectors.dep_diff_collector import DepDiffCollector
    bundle = DepDiffCollector.collect(tmp_path, profile=None)
    assert bundle.available is False
    assert bundle.nodes == []


def test_dep_diff_parse_package_json_diff():
    """_parse_manifest_diff correctly identifies added/removed packages."""
    from analyzer.evidence.collectors.dep_diff_collector import _parse_manifest_diff
    old = json.dumps({"dependencies": {"express": "4.18.0", "axios": "1.4.0"}})
    new = json.dumps({"dependencies": {"express": "4.19.0", "lodash": "4.17.21"}})
    changes = _parse_manifest_diff("package.json", old, new)
    names = {c["package"] for c in changes}
    assert "express" in names  # bumped
    assert "axios" in names   # removed
    assert "lodash" in names  # added
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_dep_diff_collector.py::test_dep_diff_unavailable_without_git -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/evidence/collectors/dep_diff_collector.py`**

```python
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
```

- [ ] **Step 4: Register collector**

In `analyzer/evidence/__init__.py`, import and register:

```python
from .collectors.dep_diff_collector import DepDiffCollector
_REGISTRY.register(DepDiffCollector)
```

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_dep_diff_collector.py -v
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add analyzer/evidence/collectors/dep_diff_collector.py tests/analyzer/test_dep_diff_collector.py analyzer/evidence/__init__.py
git commit -m "feat(v2): add DepDiffCollector — detects dependency manifest changes"
```

---

### Task 2: ContractDiffCollector + CIContextCollector

**Files:**
- Create: `analyzer/evidence/collectors/contract_diff_collector.py`
- Create: `analyzer/evidence/collectors/ci_context_collector.py`
- Create: `tests/analyzer/test_ci_context_collector.py`

**Interfaces:**
- Produces: `ContractDiffCollector` (`name="contract_diff"`, `tier="tier1"`), `CIContextCollector` (`name="ci_context"`, `tier="tier2"`)

- [ ] **Step 1: Write failing tests**

Create `tests/analyzer/test_ci_context_collector.py`:

```python
"""Tests for CIContextCollector."""
import os
import pytest


def test_ci_context_unavailable_locally(monkeypatch):
    """Not available when no CI env vars are set."""
    from analyzer.evidence.collectors.ci_context_collector import CIContextCollector
    from pathlib import Path
    for var in ("GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI", "JENKINS_URL"):
        monkeypatch.delenv(var, raising=False)
    assert CIContextCollector.is_available(Path("."), profile=None) is False


def test_ci_context_available_on_github_actions(monkeypatch, tmp_path):
    from analyzer.evidence.collectors.ci_context_collector import CIContextCollector
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    assert CIContextCollector.is_available(tmp_path, profile=None) is True


def test_ci_context_collect_returns_bundle(monkeypatch, tmp_path):
    from analyzer.evidence.collectors.ci_context_collector import CIContextCollector
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "def456")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/42/merge")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    bundle = CIContextCollector.collect(tmp_path, profile=None)
    assert bundle.collector_name == "ci_context"
    assert "provider" in bundle.summary


def test_ci_context_collect_never_raises(monkeypatch, tmp_path):
    from analyzer.evidence.collectors.ci_context_collector import CIContextCollector
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    # Force an error by making GITHUB_TOKEN invalid — should not raise
    monkeypatch.setenv("GITHUB_TOKEN", "invalid-token-that-will-fail")
    bundle = CIContextCollector.collect(tmp_path, profile=None)
    assert bundle is not None
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_ci_context_collector.py::test_ci_context_unavailable_locally -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/evidence/collectors/contract_diff_collector.py`**

```python
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


def _find_spec_files(workspace: Path) -> list[Path]:
    found = []
    for pattern in _SPEC_GLOBS:
        found.extend(workspace.rglob(pattern))
    for d in _PACT_DIRS:
        pact_dir = workspace / d
        if pact_dir.is_dir():
            found.extend(pact_dir.rglob("*.json"))
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
```

- [ ] **Step 4: Create `analyzer/evidence/collectors/ci_context_collector.py`**

```python
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
```

- [ ] **Step 5: Register both collectors in `analyzer/evidence/__init__.py`**

```python
from .collectors.contract_diff_collector import ContractDiffCollector
from .collectors.ci_context_collector import CIContextCollector
_REGISTRY.register(ContractDiffCollector)
_REGISTRY.register(CIContextCollector)
```

- [ ] **Step 6: Run tests**

```
pytest tests/analyzer/test_ci_context_collector.py -v
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add analyzer/evidence/collectors/contract_diff_collector.py analyzer/evidence/collectors/ci_context_collector.py tests/analyzer/test_ci_context_collector.py analyzer/evidence/__init__.py
git commit -m "feat(v2): add ContractDiffCollector and CIContextCollector"
```

---

### Task 3: OtelCollector + FlakyHistoryCollector

**Files:**
- Create: `analyzer/evidence/collectors/otel_collector.py`
- Create: `analyzer/evidence/collectors/flaky_history_collector.py`
- Modify: `analyzer/orchestrator.py` (write history at end, pass to flaky detector)

**Interfaces:**
- Produces: `OtelCollector` (`name="otel"`, `tier="tier1"`), `FlakyHistoryCollector` (`name="flaky_history"`, `tier="tier2"`)

- [ ] **Step 1: Write failing tests**

Create `tests/analyzer/test_otel_collector.py`:

```python
"""Tests for OtelCollector and FlakyHistoryCollector."""
import json
import pytest
from pathlib import Path


def test_otel_unavailable_when_no_traces(tmp_path):
    from analyzer.evidence.collectors.otel_collector import OtelCollector
    import os
    env_backup = os.environ.pop("ATFA_OTEL_ENDPOINT", None)
    try:
        assert OtelCollector.is_available(tmp_path, profile=None) is False
    finally:
        if env_backup:
            os.environ["ATFA_OTEL_ENDPOINT"] = env_backup


def test_otel_available_when_trace_file_exists(tmp_path):
    from analyzer.evidence.collectors.otel_collector import OtelCollector
    (tmp_path / "traces.json").write_text('{"resourceSpans": []}')
    assert OtelCollector.is_available(tmp_path, profile=None) is True


def test_otel_collect_parses_spans(tmp_path):
    from analyzer.evidence.collectors.otel_collector import OtelCollector
    spans = {
        "resourceSpans": [{
            "scopeSpans": [{
                "spans": [{
                    "name": "POST /api/users",
                    "status": {"code": 2, "message": "Error"},
                    "attributes": [
                        {"key": "http.url", "value": {"stringValue": "/api/users"}},
                        {"key": "http.status_code", "value": {"intValue": 500}}
                    ]
                }]
            }]
        }]
    }
    (tmp_path / "traces.json").write_text(json.dumps(spans))
    bundle = OtelCollector.collect(tmp_path, profile=None)
    assert bundle.available is True
    assert len(bundle.nodes) >= 1


def test_otel_collect_never_raises_on_invalid_file(tmp_path):
    from analyzer.evidence.collectors.otel_collector import OtelCollector
    (tmp_path / "traces.json").write_text("not valid json {{{")
    bundle = OtelCollector.collect(tmp_path, profile=None)
    assert bundle is not None


def test_flaky_history_unavailable_when_no_file(tmp_path):
    from analyzer.evidence.collectors.flaky_history_collector import FlakyHistoryCollector
    assert FlakyHistoryCollector.is_available(tmp_path, profile=None) is False


def test_flaky_history_available_when_file_exists(tmp_path):
    from analyzer.evidence.collectors.flaky_history_collector import FlakyHistoryCollector
    atfa = tmp_path / ".atfa"
    atfa.mkdir()
    (atfa / "history.json").write_text('{"runs": []}')
    assert FlakyHistoryCollector.is_available(tmp_path, profile=None) is True


def test_flaky_history_collect_returns_bundle(tmp_path):
    from analyzer.evidence.collectors.flaky_history_collector import FlakyHistoryCollector
    atfa = tmp_path / ".atfa"
    atfa.mkdir()
    history = {
        "runs": [
            {"run_id": "r1", "failures": [{"id": "abc", "status": "failed"}]},
            {"run_id": "r2", "failures": []},
        ]
    }
    (atfa / "history.json").write_text(json.dumps(history))
    bundle = FlakyHistoryCollector.collect(tmp_path, profile=None)
    assert bundle.available is True
    assert "history" in bundle.legacy
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_otel_collector.py::test_otel_unavailable_when_no_traces -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/evidence/collectors/otel_collector.py`**

```python
"""OtelCollector — reads OpenTelemetry trace exports for span correlation. Tier-1."""
from __future__ import annotations
import json
import os
import urllib.request
from pathlib import Path

from ..bundle import EvidenceBundle
from ..collector import EvidenceCollector
from ..graph import EvidenceNode

_TRACE_FILES = ["traces.json", "otel-traces.json", "otel_traces.json"]


def _find_trace_file(workspace: Path) -> Path | None:
    for name in _TRACE_FILES:
        p = workspace / name
        if p.exists():
            return p
    # Also check *.otlp.json
    for p in workspace.glob("*.otlp.json"):
        return p
    return None


def _extract_spans(data: dict) -> list[dict]:
    """Extract span dicts from OTLP JSON export format."""
    spans = []
    for resource_span in data.get("resourceSpans", []):
        for scope_span in resource_span.get("scopeSpans", []):
            spans.extend(scope_span.get("spans", []))
    return spans


def _attr_value(attrs: list[dict], key: str):
    for a in attrs:
        if a.get("key") == key:
            v = a.get("value", {})
            return v.get("stringValue") or v.get("intValue") or v.get("boolValue")
    return None


class OtelCollector(EvidenceCollector):
    """Reads OTel trace export files or HTTP endpoint. Tier-1 when available."""
    name = "otel"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        if _find_trace_file(workspace):
            return True
        return bool(os.environ.get("ATFA_OTEL_ENDPOINT"))

    @classmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        try:
            return cls._collect_safe(workspace)
        except Exception:
            return EvidenceBundle.empty("otel", "tier1")

    @classmethod
    def _collect_safe(cls, workspace: Path) -> EvidenceBundle:
        data = None
        trace_file = _find_trace_file(workspace)
        if trace_file:
            try:
                data = json.loads(trace_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return EvidenceBundle(
                    collector_name="otel", tier="tier1", available=False,
                    summary={"status": "invalid trace file"},
                    legacy={"available": False, "summary": {"status": "invalid trace file"}},
                )
        elif os.environ.get("ATFA_OTEL_ENDPOINT"):
            endpoint = os.environ["ATFA_OTEL_ENDPOINT"]
            try:
                with urllib.request.urlopen(endpoint, timeout=5) as resp:
                    data = json.loads(resp.read())
            except Exception:
                return EvidenceBundle.empty("otel", "tier1")

        if not data:
            return EvidenceBundle.empty("otel", "tier1")

        spans = _extract_spans(data)
        nodes: list[EvidenceNode] = []
        for i, span in enumerate(spans[:50]):  # cap at 50 spans
            status = span.get("status") or {}
            status_code = status.get("code", 0)  # 2 = ERROR in OTLP
            attrs = span.get("attributes", [])
            http_url = _attr_value(attrs, "http.url") or _attr_value(attrs, "http.target") or ""
            http_status = _attr_value(attrs, "http.status_code")
            is_error = status_code == 2 or (isinstance(http_status, int) and http_status >= 400)
            weight = 2.0 if is_error else 1.0
            excerpt = (
                f"{span.get('name', '')} "
                f"{'status=' + str(http_status) if http_status else ''} "
                f"{'ERROR' if is_error else ''}"
            ).strip()
            nodes.append(EvidenceNode(
                id=f"span:{span.get('spanId', str(i))}",
                type="span",
                ref=http_url or span.get("name", f"span:{i}"),
                weight=weight,
                excerpt=excerpt[:200],
            ))

        return EvidenceBundle(
            collector_name="otel",
            tier="tier1",
            available=bool(nodes),
            nodes=nodes,
            summary={"spans": len(spans), "error_spans": sum(1 for n in nodes if n.weight >= 2.0)},
            legacy={"available": bool(nodes),
                    "spans": [n.ref for n in nodes if n.weight >= 2.0],
                    "summary": {"spans": len(spans)}},
        )
```

- [ ] **Step 4: Create `analyzer/evidence/collectors/flaky_history_collector.py`**

```python
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
```

- [ ] **Step 5: Register collectors + wire history into orchestrator**

In `analyzer/evidence/__init__.py`:
```python
from .collectors.otel_collector import OtelCollector
from .collectors.flaky_history_collector import FlakyHistoryCollector
_REGISTRY.register(OtelCollector)
_REGISTRY.register(FlakyHistoryCollector)
```

In `analyzer/orchestrator.py`, after Phase 8 completes and before `return AnalysisResult(...)`, add history write-back:

```python
    # Write-back run history for future flaky detection
    import uuid as _uuid
    import datetime as _dt
    from .evidence.collectors.flaky_history_collector import append_run
    _run_id = _uuid.uuid4().hex[:12]
    _timestamp = _dt.datetime.utcnow().isoformat()
    try:
        append_run(workspace, _run_id, _timestamp, detected_fw, failures)
    except Exception:
        pass  # history write-back is best-effort
```

Also update the Phase 2.5 flaky detection call to pass history from the bundle:

```python
    # After Phase 5.5, extract history for flaky detector
    _history_bundle = bundles.get("flaky_history")
    _history_data = (_history_bundle.legacy.get("history") if _history_bundle and _history_bundle.available else None)
    failures = detect_flaky(failures, history=_history_data)
```

- [ ] **Step 6: Run tests**

```
pytest tests/analyzer/test_otel_collector.py -v
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add analyzer/evidence/collectors/otel_collector.py analyzer/evidence/collectors/flaky_history_collector.py tests/analyzer/test_otel_collector.py analyzer/evidence/__init__.py analyzer/orchestrator.py
git commit -m "feat(v2): add OtelCollector, FlakyHistoryCollector, history write-back"
```

---

### Task 4: CTRF output format (`analyzer/render/ctrf.py`)

**Files:**
- Create: `analyzer/render/ctrf.py`
- Modify: `analyzer/ui/cli.py` (add `--format ctrf`)
- Create: `tests/analyzer/test_ctrf_render.py`

**Interfaces:**
- Consumes: `AnalysisResult` from `analyzer.orchestrator`
- Produces: `render_ctrf_report(result: AnalysisResult) -> str` — returns CTRF JSON string

- [ ] **Step 1: Write failing tests**

Create `tests/analyzer/test_ctrf_render.py`:

```python
"""Tests for CTRF render output."""
import json
import pytest


def _make_result(framework="playwright", hypotheses=None):
    """Create a minimal AnalysisResult for testing."""
    import time
    from analyzer.orchestrator import AnalysisResult
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    from analyzer.workspace_scanner import WorkspaceProfile
    f = NormalizedFailure(
        id=make_failure_id(framework, "suite", "test_a", "test.spec.ts"),
        framework=framework, suite="suite", title="test_a",
        file="test.spec.ts", status="failed",
        error_message="Expected 201 but got 404",
    )
    return AnalysisResult(
        framework=framework,
        failures=[f],
        git={"available": False, "commits": [], "summary": {}},
        logs={"available": False, "matches": [], "summary": {}},
        config={"available": False, "files": [], "summary": {}},
        matrix=[],
        clusters=[],
        hypotheses=hypotheses or [],
        report_markdown="# report",
        elapsed_seconds=1.5,
        profile=WorkspaceProfile(
            mode="FULL_SOURCE", source_roots=[], test_roots=[], noise_paths=[],
            openapi_spec=None, has_git=False,
        ),
        phase_timings={},
    )


def test_ctrf_render_produces_valid_json():
    from analyzer.render.ctrf import render_ctrf_report
    result = _make_result()
    output = render_ctrf_report(result)
    parsed = json.loads(output)
    assert "results" in parsed
    assert "tool" in parsed["results"]
    assert "summary" in parsed["results"]
    assert "tests" in parsed["results"]


def test_ctrf_render_summary_counts_match():
    from analyzer.render.ctrf import render_ctrf_report
    result = _make_result()
    parsed = json.loads(render_ctrf_report(result))
    summary = parsed["results"]["summary"]
    assert summary["tests"] == 1
    assert summary["failed"] == 1
    assert summary["passed"] == 0


def test_ctrf_render_test_has_ai_field_when_hypothesis_exists():
    from analyzer.render.ctrf import render_ctrf_report
    from analyzer.hypothesis import Hypothesis
    h = Hypothesis(
        cluster_id="C1",
        title="Endpoint moved",
        summary="Route renamed in recent commit",
        confidence=87,
        confidence_justification="git+logs",
        affected_tests=["test_a"],
        remediation=["Update URL in test"],
        buggy_location="api/routes.py:44",
    )
    result = _make_result(hypotheses=[h])
    parsed = json.loads(render_ctrf_report(result))
    test = parsed["results"]["tests"][0]
    assert "ai" in test
    assert "87" in test["ai"] or "87%" in test["ai"]


def test_ctrf_render_tool_name_is_correct():
    from analyzer.render.ctrf import render_ctrf_report
    result = _make_result(framework="jest")
    parsed = json.loads(render_ctrf_report(result))
    assert parsed["results"]["tool"]["name"] == "ai-test-failure-analyzer"
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_ctrf_render.py::test_ctrf_render_produces_valid_json -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/render/ctrf.py`**

```python
"""CTRF (Common Test Results Format) output renderer.

Spec: https://github.com/ctrf-io/ctrf — pre-1.0, pinned to schema as of 2026-01.
The 'ai' string field (§9.11) contains a one-line hypothesis summary per test.
"""
from __future__ import annotations
import json
import time
from analyzer.orchestrator import AnalysisResult
from analyzer.hypothesis import Hypothesis

_TOOL_NAME = "ai-test-failure-analyzer"


def _get_tool_version() -> str:
    try:
        from importlib.metadata import version
        return version("ai-test-failure-analyzer")
    except Exception:
        return "2.0.0"


def _find_hypothesis_for_test(title: str, hypotheses: list[Hypothesis]) -> Hypothesis | None:
    for h in hypotheses:
        if title in h.affected_tests:
            return h
    return None


def render_ctrf_report(result: AnalysisResult) -> str:
    """Render analysis result as CTRF JSON string."""
    now_ms = int(time.time() * 1000)
    elapsed_ms = int(result.elapsed_seconds * 1000)

    failures = result.failures
    passed = sum(1 for f in failures if f.status == "passed")
    failed = sum(1 for f in failures if f.status == "failed")
    skipped = sum(1 for f in failures if f.status == "skipped")
    flaky = sum(1 for f in failures if f.status == "flaky" or (f.flakiness_score or 0) >= 0.5)

    tests_out = []
    for f in failures:
        hyp = _find_hypothesis_for_test(f.title, result.hypotheses)
        ai_str = None
        if hyp:
            ai_str = (
                f"Root cause [{hyp.confidence}%]: {hyp.title}. "
                f"{hyp.summary[:120]} "
                f"Evidence: {'+'.join(sorted({e.source for e in hyp.evidence_chain})) or 'none'}."
            )
        test_obj: dict = {
            "name": f.title,
            "status": f.status,
            "duration": f.duration_ms or 0,
        }
        if f.status == "failed":
            if f.error_message:
                test_obj["message"] = f.error_message[:500]
            if f.error_stack:
                test_obj["trace"] = f.error_stack[:1000]
        if f.status == "flaky" or (f.flakiness_score or 0) >= 0.5:
            test_obj["flaky"] = True
        if f.file and f.file != "unknown":
            test_obj["filePath"] = f.file
        if f.suite:
            test_obj["suite"] = f.suite
        if ai_str:
            test_obj["ai"] = ai_str[:500]
        # CTRF extra block — structured data for programmatic consumers
        extra: dict = {}
        if hyp:
            extra["hypothesis_confidence"] = hyp.confidence
            extra["hypothesis_title"] = hyp.title
            if hyp.buggy_location:
                extra["buggy_location"] = hyp.buggy_location
            extra["evidence_sources"] = sorted({e.source for e in hyp.evidence_chain})
        if f.flakiness_score is not None:
            extra["flakiness_score"] = round(f.flakiness_score, 3)
        if f.flakiness_category:
            extra["flakiness_category"] = f.flakiness_category
        if extra:
            test_obj["extra"] = extra
        # Preserve original ctrf_extra fields
        if f.ctrf_extra:
            test_obj.setdefault("extra", {}).update(f.ctrf_extra)
        tests_out.append(test_obj)

    ctrf = {
        "results": {
            "tool": {"name": _TOOL_NAME, "version": _get_tool_version()},
            "summary": {
                "tests": len(failures),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "flaky": flaky,
                "start": now_ms - elapsed_ms,
                "stop": now_ms,
            },
            "tests": tests_out,
        }
    }
    return json.dumps(ctrf, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Add `--format ctrf` to CLI in `analyzer/ui/cli.py`**

Find the `--format` argument or `--out` argument. Add `ctrf` as a valid format choice, and in the output section add:

```python
if args.format == "ctrf" or (args.out and args.out.endswith(".ctrf.json")):
    from ..render.ctrf import render_ctrf_report
    output = render_ctrf_report(result)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    else:
        print(output)
```

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_ctrf_render.py -v
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add analyzer/render/ctrf.py tests/analyzer/test_ctrf_render.py analyzer/ui/cli.py
git commit -m "feat(v2): add CTRF output renderer and --format ctrf / --out *.ctrf.json flag"
```

---

### Task 5: Result caching + `--watch` mode + `--no-cache` flag

**Files:**
- Create: `analyzer/cache.py`
- Modify: `analyzer/orchestrator.py`, `analyzer/ui/cli.py`
- Create: `tests/analyzer/test_cache.py`

**Interfaces:**
- Produces: `CacheKey.compute(workspace, results_path) -> str`, `load_cached(workspace, key) -> AnalysisResult | None`, `save_cache(workspace, key, result) -> None`

- [ ] **Step 1: Write failing tests**

Create `tests/analyzer/test_cache.py`:

```python
"""Tests for result caching."""
import json
import pytest
from pathlib import Path


def test_cache_key_is_deterministic(tmp_path):
    from analyzer.cache import CacheKey
    (tmp_path / "results.json").write_text('{"test": 1}')
    k1 = CacheKey.compute(tmp_path, tmp_path / "results.json")
    k2 = CacheKey.compute(tmp_path, tmp_path / "results.json")
    assert k1 == k2
    assert len(k1) == 40  # SHA1 hex


def test_cache_key_changes_when_file_content_changes(tmp_path):
    from analyzer.cache import CacheKey
    p = tmp_path / "results.json"
    p.write_text('{"test": 1}')
    k1 = CacheKey.compute(tmp_path, p)
    p.write_text('{"test": 2}')
    k2 = CacheKey.compute(tmp_path, p)
    assert k1 != k2


def test_save_and_load_cache(tmp_path):
    from analyzer.cache import save_cache, load_cached, CacheKey
    from analyzer.orchestrator import AnalysisResult
    from analyzer.workspace_scanner import WorkspaceProfile
    p = tmp_path / "results.json"
    p.write_text('{"x": 1}')
    key = CacheKey.compute(tmp_path, p)
    result = AnalysisResult(
        framework="jest", failures=[], git={}, logs={}, config={},
        matrix=[], clusters=[], hypotheses=[], report_markdown="# r",
        elapsed_seconds=1.0,
        profile=WorkspaceProfile(mode="API_ONLY", source_roots=[], test_roots=[],
                                  noise_paths=[], openapi_spec=None, has_git=False),
        phase_timings={},
    )
    save_cache(tmp_path, key, result)
    loaded = load_cached(tmp_path, key)
    assert loaded is not None
    assert loaded.framework == "jest"


def test_load_cached_returns_none_when_missing(tmp_path):
    from analyzer.cache import load_cached
    assert load_cached(tmp_path, "nonexistent_key") is None
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_cache.py::test_cache_key_is_deterministic -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/cache.py`**

```python
"""Analysis result caching — SHA1 key, 24h expiry, .atfa/cache/ storage."""
from __future__ import annotations
import dataclasses
import hashlib
import json
import os
import time
from pathlib import Path

_CACHE_DIR = ".atfa/cache"
_EXPIRY_SECONDS = 86400  # 24 hours


class CacheKey:
    @staticmethod
    def compute(workspace: Path, results_path: Path) -> str:
        """SHA1 of: git HEAD (if exists) + results file mtime + results file size."""
        parts: list[str] = []
        git_head = workspace / ".git" / "HEAD"
        if git_head.exists():
            try:
                ref = git_head.read_text().strip()
                # Resolve symbolic ref
                if ref.startswith("ref:"):
                    ref_path = workspace / ".git" / ref[5:].strip()
                    if ref_path.exists():
                        ref = ref_path.read_text().strip()
                parts.append(ref)
            except OSError:
                pass
        try:
            stat = results_path.stat()
            parts.append(f"{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            parts.append(str(results_path))
        seed = ":".join(parts)
        return hashlib.sha1(seed.encode()).hexdigest()


def _cache_path(workspace: Path, key: str) -> Path:
    return workspace / _CACHE_DIR / f"{key}.json"


def load_cached(workspace: Path, key: str):
    """Return cached AnalysisResult or None if missing/expired/invalid."""
    p = _cache_path(workspace, key)
    if not p.exists():
        return None
    try:
        age = time.time() - p.stat().st_mtime
        if age > _EXPIRY_SECONDS:
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        # Reconstruct AnalysisResult from dict (minimal fields only)
        from .orchestrator import AnalysisResult
        from .workspace_scanner import WorkspaceProfile
        profile_data = data.get("profile") or {}
        profile = WorkspaceProfile(
            mode=profile_data.get("mode", "API_ONLY"),
            source_roots=[],
            test_roots=[],
            noise_paths=[],
            openapi_spec=None,
            has_git=profile_data.get("has_git", False),
        )
        return AnalysisResult(
            framework=data["framework"],
            failures=[],  # failures not cached (large); re-parse on hit is fast
            git=data.get("git", {}),
            logs=data.get("logs", {}),
            config=data.get("config", {}),
            matrix=data.get("matrix", []),
            clusters=data.get("clusters", []),
            hypotheses=[],  # hypotheses reconstructed from report
            report_markdown=data.get("report_markdown", ""),
            elapsed_seconds=data.get("elapsed_seconds", 0),
            profile=profile,
            phase_timings=data.get("phase_timings", {}),
        )
    except Exception:
        return None


def save_cache(workspace: Path, key: str, result) -> None:
    """Persist AnalysisResult to cache. Best-effort — never raises."""
    try:
        p = _cache_path(workspace, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "framework": result.framework,
            "git": result.git,
            "logs": result.logs,
            "config": result.config,
            "matrix": result.matrix,
            "clusters": result.clusters,
            "report_markdown": result.report_markdown,
            "elapsed_seconds": result.elapsed_seconds,
            "phase_timings": getattr(result, "phase_timings", {}),
            "profile": dataclasses.asdict(result.profile) if result.profile else {},
        }
        p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass
```

- [ ] **Step 4: Wire caching into orchestrator + add `--no-cache` CLI flag**

In `analyzer/orchestrator.py`, wrap the beginning of `analyze()`:

```python
    # Cache check (skip if no_cache=True)
    from .cache import CacheKey, load_cached, save_cache
    no_cache = kwargs.pop("no_cache", False) if "no_cache" in kwargs else False
    cache_key = CacheKey.compute(workspace, safe_results_path if 'safe_results_path' in dir() else Path(results_path))
```

Because `safe_results_path` isn't set yet at that point, do this after the path validation block instead. Add to `analyze()` signature: `no_cache: bool = False`. After Phase 1 emit, add:

```python
    cache_key = CacheKey.compute(workspace, safe_results_path)
    if not no_cache:
        cached = load_cached(workspace, cache_key)
        if cached is not None:
            emit({"phase": "cache", "name": "Cache hit", "status": "completed"})
            return cached
```

At the end of `analyze()`, after Phase 8, add:

```python
    if not no_cache:
        save_cache(workspace, cache_key, result)
```

Also add `no_cache=False` to the `analyze()` signature.

In `analyzer/ui/cli.py`, add `--no-cache` flag:

```python
parser.add_argument("--no-cache", action="store_true", default=False,
                    help="Skip reading and writing the analysis cache")
```

Pass `no_cache=args.no_cache` to `analyze()`.

- [ ] **Step 5: Add `--watch` mode to CLI**

In `analyzer/ui/cli.py`, add a `watch` subcommand (or check if the main command has a `--watch` flag). Add:

```python
# In the watch subcommand or as a separate function:
def cmd_watch(args):
    """Watch results file and re-analyze on change."""
    import time as _time
    import os as _os
    results_path = Path(args.results_file)
    last_mtime = None
    print(f"Watching {results_path} — press Ctrl+C to stop")
    while True:
        try:
            mtime = _os.stat(results_path).st_mtime
        except OSError:
            _time.sleep(2)
            continue
        if mtime != last_mtime:
            last_mtime = mtime
            print(f"\n--- Change detected, re-analyzing ---")
            # Clear screen
            print("\033[2J\033[H", end="")
            cmd_analyze(args)  # re-run analysis
        _time.sleep(2)
```

- [ ] **Step 6: Run tests**

```
pytest tests/analyzer/test_cache.py -v
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add analyzer/cache.py tests/analyzer/test_cache.py analyzer/orchestrator.py analyzer/ui/cli.py
git commit -m "feat(v2): add result caching, --no-cache flag, --watch mode"
```

---

### Task 6: Optional LLM enrichment (`analyzer/enricher.py`)

**Files:**
- Create: `analyzer/enricher.py`
- Modify: `analyzer/ui/cli.py` (add `--enrich` flag)
- Create: `tests/analyzer/test_enricher.py`

**Interfaces:**
- Produces: `enrich(result: AnalysisResult, config: EnrichConfig) -> str` — returns enrichment markdown string

- [ ] **Step 1: Write failing tests**

Create `tests/analyzer/test_enricher.py`:

```python
"""Tests for optional LLM enrichment."""
import json
import pytest
from unittest.mock import patch, MagicMock


def _minimal_result():
    from analyzer.orchestrator import AnalysisResult
    from analyzer.workspace_scanner import WorkspaceProfile
    return AnalysisResult(
        framework="playwright", failures=[], git={}, logs={}, config={},
        matrix=[], clusters=[], hypotheses=[],
        report_markdown="# report", elapsed_seconds=1.0,
        profile=WorkspaceProfile(mode="FULL_SOURCE", source_roots=[],
                                  test_roots=[], noise_paths=[],
                                  openapi_spec=None, has_git=False),
        phase_timings={},
    )


def test_enrich_config_no_key_raises():
    from analyzer.enricher import EnrichConfig
    with pytest.raises(ValueError, match="No LLM"):
        EnrichConfig.from_env()  # no env vars set


def test_enrich_config_reads_env(monkeypatch):
    from analyzer.enricher import EnrichConfig
    monkeypatch.setenv("ATFA_LLM_KEY", "test-key")
    monkeypatch.setenv("ATFA_LLM_ENDPOINT", "https://api.example.com/v1/chat")
    config = EnrichConfig.from_env()
    assert config.api_key == "test-key"
    assert "example.com" in config.endpoint


def test_enrich_returns_string_on_success(monkeypatch):
    """enrich() returns a markdown string when the LLM call succeeds."""
    from analyzer.enricher import enrich, EnrichConfig
    result = _minimal_result()
    config = EnrichConfig(
        provider="custom",
        endpoint="https://api.example.com",
        api_key="test-key",
        model="test-model",
    )
    mock_response = json.dumps({
        "choices": [{"message": {"content": "## AI Enrichment\n\nRoot cause confirmed."}}]
    }).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        output = enrich(result, config)
    assert "AI Enrichment" in output or "Root cause" in output


def test_enrich_returns_empty_on_http_error(monkeypatch):
    """enrich() returns empty string (not raises) on HTTP failure."""
    from analyzer.enricher import enrich, EnrichConfig
    import urllib.error
    result = _minimal_result()
    config = EnrichConfig(provider="custom", endpoint="https://bad", api_key="k", model="m")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        output = enrich(result, config)
    assert output == ""
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_enricher.py::test_enrich_config_no_key_raises -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/enricher.py`**

```python
"""Optional LLM enrichment — appended to report only when --enrich flag is set.

Uses urllib.request (stdlib) to call any compatible LLM endpoint.
Never required for the deterministic analysis to work.
"""
from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from analyzer.orchestrator import AnalysisResult

_PROMPT_TEMPLATE = """\
You are a software debugging expert. Below is a deterministic test failure analysis \
report produced by ai-test-failure-analyzer. The report already identifies the most \
likely root causes. Your task is to:
1. Confirm or gently correct the top hypothesis in plain language.
2. Suggest a specific code fix (show the file path and the change needed).
3. Mention any related documentation or patterns to watch for.

Be concise — under 300 words. Start your response with "## AI Enrichment".

FRAMEWORK: {framework}
MODE: {mode}
TOP HYPOTHESIS: {hypothesis_json}
"""

_OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
_CLAUDE_ENDPOINT = "https://api.anthropic.com/v1/messages"


@dataclass
class EnrichConfig:
    provider: str   # "claude" | "openai" | "ollama" | "custom"
    endpoint: str
    api_key: str
    model: str

    @classmethod
    def from_env(cls) -> "EnrichConfig":
        key = os.environ.get("ATFA_LLM_KEY") or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("No LLM API key configured. Set ATFA_LLM_KEY or OPENAI_API_KEY.")
        endpoint = os.environ.get("ATFA_LLM_ENDPOINT", _OPENAI_ENDPOINT)
        model = os.environ.get("ATFA_LLM_MODEL", "gpt-4o")
        if os.environ.get("ATFA_LLM_KEY") and not os.environ.get("ATFA_LLM_ENDPOINT"):
            # Default to Claude if ATFA_LLM_KEY set without custom endpoint
            endpoint = _CLAUDE_ENDPOINT
            model = os.environ.get("ATFA_LLM_MODEL", "claude-sonnet-4-6")
        provider = "claude" if "anthropic" in endpoint else (
            "openai" if "openai" in endpoint else "custom"
        )
        return cls(provider=provider, endpoint=endpoint, api_key=key, model=model)


def _build_prompt(result: AnalysisResult) -> str:
    top_hyp = result.hypotheses[0].to_dict() if result.hypotheses else {}
    return _PROMPT_TEMPLATE.format(
        framework=result.framework,
        mode=result.profile.mode if result.profile else "unknown",
        hypothesis_json=json.dumps(top_hyp, indent=2)[:800],
    )


def _call_openai(config: EnrichConfig, prompt: str) -> str:
    body = json.dumps({
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
    }).encode()
    req = urllib.request.Request(
        config.endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _call_claude(config: EnrichConfig, prompt: str) -> str:
    body = json.dumps({
        "model": config.model,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        config.endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"]


def enrich(result: AnalysisResult, config: EnrichConfig) -> str:
    """Call configured LLM endpoint and return enrichment markdown.

    Returns empty string on any failure — never raises.
    """
    if not result.hypotheses:
        return ""
    try:
        prompt = _build_prompt(result)
        if config.provider == "claude":
            return _call_claude(config, prompt)
        else:
            return _call_openai(config, prompt)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError):
        return ""
    except Exception:
        return ""
```

- [ ] **Step 4: Add `--enrich` flag to CLI**

In `analyzer/ui/cli.py`, add:

```python
parser.add_argument("--enrich", action="store_true", default=False,
                    help="Send top hypothesis to configured LLM for natural-language explanation "
                         "(requires ATFA_LLM_KEY or OPENAI_API_KEY)")
```

After report generation, add:

```python
if args.enrich:
    from ..enricher import enrich, EnrichConfig
    try:
        config = EnrichConfig.from_env()
        enrichment = enrich(result, config)
        if enrichment:
            report += "\n\n" + enrichment
    except ValueError as e:
        print(f"  {e}", file=sys.stderr)
```

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_enricher.py -v
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add analyzer/enricher.py tests/analyzer/test_enricher.py analyzer/ui/cli.py
git commit -m "feat(v2): add optional LLM enrichment via --enrich flag (urllib.request, zero new deps)"
```

---

### Task 7: Language-specific remediation + TUI phase timings

**Files:**
- Create: `analyzer/remediation.py`
- Modify: `analyzer/hypothesis.py`, `analyzer/render/markdown.py`, `analyzer/ui/tui.py`

**Interfaces:**
- Produces: `language_for_framework(framework: str) -> str`, `remediation_prefix(framework: str) -> str`

- [ ] **Step 1: Create `analyzer/remediation.py`**

```python
"""Language-specific remediation template selector."""
from __future__ import annotations

_FRAMEWORK_LANGUAGE: dict[str, str] = {
    "playwright": "js", "cypress": "js", "jest": "js", "vitest": "js",
    "mocha": "js", "wdio": "js", "detox": "js",
    "pytest": "python", "robot": "python",
    "go": "go",
    "junit": "jvm", "rest-assured": "jvm", "karate": "jvm", "testng": "jvm",
    "nunit": "dotnet", "xunit": "dotnet", "mstest": "dotnet",
    "rspec": "ruby", "phpunit": "php",
    "k6": "load", "artillery": "load", "gatling": "load",
    "newman": "api", "pact": "api",
}

_INSTALL_PREFIX: dict[str, str] = {
    "js": "npm install / npx",
    "python": "pip install / pytest",
    "go": "go test / go mod tidy",
    "jvm": "mvn test / gradle test",
    "dotnet": "dotnet test",
    "ruby": "bundle exec rspec",
    "php": "./vendor/bin/phpunit",
    "load": "check thresholds and SLA config",
    "api": "check endpoint URL and auth token",
}

_RUN_COMMAND: dict[str, str] = {
    "playwright": "npx playwright test --debug",
    "cypress": "npx cypress run --headed",
    "jest": "npx jest --verbose",
    "vitest": "npx vitest run --reporter verbose",
    "pytest": "pytest -s -v",
    "robot": "robot --loglevel DEBUG",
    "go": "go test -v -run TestName ./...",
    "junit": "mvn test -Dtest=ClassName#methodName",
    "nunit": "dotnet test --filter FullyQualifiedName~MethodName",
    "xunit": "dotnet test --filter Method=MethodName",
    "rspec": "bundle exec rspec spec/path_to_spec.rb",
    "phpunit": "./vendor/bin/phpunit --filter methodName",
    "k6": "k6 run --verbose script.js",
    "newman": "newman run collection.json --verbose",
}


def language_for_framework(framework: str) -> str:
    return _FRAMEWORK_LANGUAGE.get(framework.lower(), "unknown")


def run_command_for_framework(framework: str) -> str | None:
    return _RUN_COMMAND.get(framework.lower())


def install_prefix_for_language(language: str) -> str:
    return _INSTALL_PREFIX.get(language, "check your test runner")
```

- [ ] **Step 2: Update `analyzer/render/markdown.py` to include language-specific run command**

Find the remediation section in the markdown renderer. After the existing remediation bullet points, add:

```python
from .remediation import run_command_for_framework
run_cmd = run_command_for_framework(framework or "")
if run_cmd:
    lines.append(f"- **Debug command:** `{run_cmd}`")
```

- [ ] **Step 3: Update TUI to display phase timings**

In `analyzer/ui/tui.py`, find where phase completion is displayed. After each phase-completed event, append the timing if present in `event["data"]` or from `result.phase_timings`. Display format:

```python
timing = phase_timings.get(f"{event['phase']}_{event['name'].lower().replace(' ', '_')}", 0)
if timing > 0:
    suffix = f"  {int(timing * 1000)}ms"
else:
    suffix = ""
print(f"  ✓ Phase {event['phase']}  {event['name']:<30}{suffix}")
```

- [ ] **Step 4: Run full suite**

```
pytest tests/analyzer -q
npm test
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add analyzer/remediation.py analyzer/render/markdown.py analyzer/ui/tui.py
git commit -m "feat(v2): add language-specific remediation, TUI phase timings"
```

---

### Task 8: GitHub App + Docker image

**Files:**
- Create: `bin/github-app/server.js`
- Create: `bin/github-app/package.json`
- Create: `Dockerfile`
- Create: `.github/workflows/docker.yml`

**Interfaces:**
- GitHub App: listens on `PORT` (default 3000), handles `check_run.completed` webhook, runs `ai-analyze analyze`, posts PR comment
- Docker: `ghcr.io/aks-builds/ai-test-failure-analyzer:latest`, accepts same args as `ai-analyze`

- [ ] **Step 1: Create `bin/github-app/package.json`**

```json
{
  "name": "ai-test-failure-analyzer-app",
  "version": "2.0.0",
  "description": "GitHub App for ai-test-failure-analyzer — posts analysis as PR comments",
  "main": "server.js",
  "engines": { "node": ">=18" },
  "dependencies": {
    "@octokit/webhooks": "^13.0.0"
  },
  "scripts": {
    "start": "node server.js"
  }
}
```

- [ ] **Step 2: Create `bin/github-app/server.js`**

```javascript
#!/usr/bin/env node
/**
 * GitHub App — listens for check_run.completed webhooks,
 * downloads test result artifacts, runs ai-analyze, posts PR comment.
 *
 * Required env vars:
 *   GITHUB_APP_ID, GITHUB_PRIVATE_KEY, GITHUB_WEBHOOK_SECRET
 *   PORT (default: 3000)
 */
"use strict";

const http = require("http");
const { createHmac } = require("crypto");
const { execFileSync } = require("child_process");
const https = require("https");
const os = require("os");
const path = require("path");
const fs = require("fs");

const PORT = parseInt(process.env.PORT || "3000", 10);
const WEBHOOK_SECRET = process.env.GITHUB_WEBHOOK_SECRET || "";

function verifySignature(body, signature) {
  if (!WEBHOOK_SECRET) return true; // dev mode only
  const expected = "sha256=" + createHmac("sha256", WEBHOOK_SECRET).update(body).digest("hex");
  return expected === signature;
}

function downloadArtifact(url, token, dest) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, {
      headers: { Authorization: `Bearer ${token}`, "User-Agent": "ai-analyze-app/2.0" },
    }, (res) => {
      if (res.statusCode === 302 || res.statusCode === 301) {
        return downloadArtifact(res.headers.location, token, dest).then(resolve).catch(reject);
      }
      const out = fs.createWriteStream(dest);
      res.pipe(out);
      out.on("finish", resolve);
      out.on("error", reject);
    });
    req.on("error", reject);
  });
}

async function handleCheckRun(payload, token) {
  const { check_run, repository } = payload;
  if (check_run.conclusion !== "failure") return;

  // Find artifact named 'test-results' or '*results*'
  const artifactsUrl = `https://api.github.com/repos/${repository.full_name}/actions/runs/${check_run.details_url?.match(/runs\/(\d+)/)?.[1]}/artifacts`;
  // Simplified: log and skip if we can't parse the run ID
  const runId = check_run.details_url?.match(/runs\/(\d+)/)?.[1];
  if (!runId) return;

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "atfa-"));
  const artifactPath = path.join(tmpDir, "results.json");

  try {
    // Download artifacts list
    const artifactsResp = await new Promise((resolve, reject) => {
      https.get(artifactsUrl, {
        headers: { Authorization: `Bearer ${token}`, "User-Agent": "ai-analyze-app/2.0",
                   Accept: "application/vnd.github+json" },
      }, (res) => {
        let data = "";
        res.on("data", d => data += d);
        res.on("end", () => { try { resolve(JSON.parse(data)); } catch (e) { reject(e); } });
      }).on("error", reject);
    });

    const artifact = (artifactsResp.artifacts || []).find(a =>
      a.name.includes("result") || a.name.includes("test")
    );
    if (!artifact) return;

    await downloadArtifact(artifact.archive_download_url, token, artifactPath);

    // Run analysis
    const analysisJson = execFileSync("ai-analyze", ["analyze", artifactPath, "--format", "json"], {
      timeout: 120000, encoding: "utf8",
    });
    const analysis = JSON.parse(analysisJson);
    const topHyp = analysis.hypotheses?.[0];
    if (!topHyp) return;

    const comment = [
      "## 🩻 Test Failure Analysis",
      "",
      `**Root Cause [${topHyp.confidence}%]:** ${topHyp.title}`,
      "",
      topHyp.summary,
      "",
      "**Remediation:**",
      ...(topHyp.remediation || []).map(r => `- ${r}`),
      ...(topHyp.buggy_location ? [`\n**Location:** \`${topHyp.buggy_location}\``] : []),
      "",
      "_Powered by [ai-test-failure-analyzer](https://github.com/aks-builds/ai-test-failure-analyzer)_",
    ].join("\n");

    // Post PR comment via Octokit (simplified — use REST directly)
    const prNumber = check_run.pull_requests?.[0]?.number;
    if (!prNumber) return;

    const commentBody = JSON.stringify({ body: comment });
    await new Promise((resolve, reject) => {
      const req = https.request({
        hostname: "api.github.com",
        path: `/repos/${repository.full_name}/issues/${prNumber}/comments`,
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(commentBody),
          "User-Agent": "ai-analyze-app/2.0",
          Accept: "application/vnd.github+json",
        },
      }, resolve);
      req.on("error", reject);
      req.write(commentBody);
      req.end();
    });
  } finally {
    try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch {}
  }
}

const server = http.createServer(async (req, res) => {
  if (req.method !== "POST" || req.url !== "/webhook") {
    res.writeHead(404);
    res.end("Not found");
    return;
  }

  let body = "";
  req.on("data", chunk => body += chunk);
  req.on("end", async () => {
    const sig = req.headers["x-hub-signature-256"] || "";
    if (!verifySignature(body, sig)) {
      res.writeHead(401);
      res.end("Invalid signature");
      return;
    }
    res.writeHead(200);
    res.end("OK");

    try {
      const payload = JSON.parse(body);
      const event = req.headers["x-github-event"];
      const token = process.env.GITHUB_TOKEN || "";
      if (event === "check_run" && payload.action === "completed") {
        await handleCheckRun(payload, token);
      }
    } catch (err) {
      console.error("Webhook handler error:", err.message);
    }
  });
});

server.listen(PORT, () => {
  console.log(`ai-analyze GitHub App listening on port ${PORT}`);
});
```

- [ ] **Step 3: Create `Dockerfile`**

```dockerfile
# Stage 1: build
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY analyzer/ analyzer/
RUN pip install --no-cache-dir build && python -m build --wheel

# Stage 2: runtime
FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/aks-builds/ai-test-failure-analyzer"
LABEL org.opencontainers.image.description="AI-powered test failure analyzer"
WORKDIR /workspace
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
ENTRYPOINT ["ai-analyze"]
CMD ["--help"]
```

- [ ] **Step 4: Create `.github/workflows/docker.yml`**

```yaml
name: Docker

on:
  release:
    types: [published]

jobs:
  build-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Extract version
        id: version
        run: echo "VERSION=$(node -p "require('./package.json').version")" >> $GITHUB_OUTPUT
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ steps.version.outputs.VERSION }}
            ghcr.io/${{ github.repository }}:${{ steps.version.outputs.VERSION.split('.')[0] }}
```

- [ ] **Step 5: Update README with Docker usage**

Add to `README.md` under the Install section:

```markdown
**Docker:**
```bash
docker run --rm -v $(pwd):/workspace \
  ghcr.io/aks-builds/ai-test-failure-analyzer \
  analyze /workspace/results.json
```
```

- [ ] **Step 6: Run full test suite**

```
pytest tests/analyzer -q
npm test
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add bin/github-app/ Dockerfile .github/workflows/docker.yml README.md
git commit -m "feat(v2): add GitHub App webhook handler and Docker image"
```

---

## Phase 4 Complete

At this point the full v2 feature set is implemented:

- **8 evidence collectors** (3 existing + DepDiff + ContractDiff + CIContext + OTel + FlakyHistory)
- **CTRF canonical output** (`--format ctrf` / `--out *.ctrf.json`)
- **Result caching** (24h, SHA1 key, `.atfa/cache/`)
- **Run history write-back** (`.atfa/history.json`, powers flaky detection)
- **`--watch` mode** (2s polling, live re-analysis)
- **Optional LLM enrichment** (`--enrich`, zero new deps)
- **Language-specific remediation** (per framework run command + fix guidance)
- **TUI phase timings** (ms per phase)
- **GitHub App** (`bin/github-app/server.js`)
- **Docker image** (`Dockerfile` + CI workflow)

---

### Task 9: Version bump + JSON output additions + README update

**Files:**
- Modify: `pyproject.toml`, `package.json` (version → 2.0.0)
- Modify: `analyzer/orchestrator.py` (`AnalysisResult.to_dict()` — add `ctrf_summary` and `flaky_tests` keys)
- Modify: `README.md` (update parser count, phase count, new flags, CTRF section)

- [ ] **Step 1: Bump version to 2.0.0**

In `pyproject.toml`, change `version = "1.0.x"` → `version = "2.0.0"`.
In `package.json`, change `"version": "1.0.x"` → `"version": "2.0.0"`.

- [ ] **Step 2: Add `ctrf_summary` and `flaky_tests` to `AnalysisResult.to_dict()`**

Find `AnalysisResult.to_dict()` (or `asdict()` usage in CLI). Add:

```python
def to_dict(self) -> dict:
    base = {
        "framework": self.framework,
        "hypotheses": [h.to_dict() for h in self.hypotheses],
        "elapsed_seconds": self.elapsed_seconds,
        "phase_timings": self.phase_timings,
        "suppressed_hypotheses": self.suppressed_hypotheses,
        "no_app_fault": self.no_app_fault,
    }
    # v2 additions
    base["flaky_tests"] = [
        {"id": f.id, "title": f.title, "score": f.flakiness_score,
         "category": f.flakiness_category}
        for f in self.failures if (f.flakiness_score or 0) >= 0.5
    ]
    from .render.ctrf import render_ctrf_report
    import json
    base["ctrf_summary"] = json.loads(render_ctrf_report(self))["results"]["summary"]
    return base
```

- [ ] **Step 3: Update README key stats**

In `README.md`, update:
- Parser count: "Playwright, Jest, Cypress, Newman, k6, or JUnit" → list all 24 (or say "24 frameworks")
- Add `--format ctrf`, `--enrich`, `--no-cache`, `--watch` to Usage section
- Add CTRF output example
- Add Docker usage block

- [ ] **Step 4: Run full suite + commit**

```
pytest tests/analyzer -q
npm test
git add pyproject.toml package.json analyzer/orchestrator.py README.md
git commit -m "chore(v2): bump version to 2.0.0, add ctrf_summary/flaky_tests to JSON output, update README"
```

---

## Phase 4 Complete

All four phases together deliver the full v2 spec from `docs/superpowers/specs/2026-06-20-v2-design.md`.
