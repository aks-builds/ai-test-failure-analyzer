"""The orchestrator — chains all ten phases of analysis into one generator.

Every UI surface (CLI / TUI / Web / MCP) calls this. The generator emits
progress events so each UI can render them in its own way without duplicating
analysis logic.

Event shapes:
    {"phase": int, "name": str, "status": "started"}
    {"phase": int, "name": str, "status": "completed", "data": <phase-specific>}
    {"phase": int, "name": str, "status": "question", "question": Question, "answer": Awaitable[str]}
    {"phase": "done", "report_markdown": str, "report_ansi": str, "hypotheses": list, ...}
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from .evidence import cluster_failures, correlate
from .hypothesis import Hypothesis, form_hypotheses
from .parsers import detect, parse
from .render.markdown import render_markdown_report
from .security import SecurityError
from .workspace_scanner import WorkspaceProfile, scan_workspace
from .noise_filter import filter_hypotheses as _filter_hypotheses


@dataclass
class AnalysisResult:
    framework: str
    failures: list
    git: dict
    logs: dict
    config: dict
    matrix: list[dict]
    clusters: list[dict]
    hypotheses: list[Hypothesis]
    report_markdown: str
    elapsed_seconds: float
    profile: WorkspaceProfile | None = None
    suppressed_hypotheses: int = 0
    no_app_fault: bool = False
    phase_timings: dict = field(default_factory=dict)

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


# An "ask" callback is what each UI provides for clarifying questions.
# It takes a Question id and returns the user's chosen answer (string).
AskFn = Callable[[str], str]


def _no_op_ask(qid: str) -> str:
    """Non-interactive fallback. Returns declared default only — never guesses from choices list."""
    from .elicit import get
    q = get(qid)
    if q.default is not None:
        return q.default
    return ""


def analyze(
    results_path: str | Path,
    workspace: str | Path | None = None,
    framework: str = "auto",
    mode: str = "auto",
    ask: AskFn | None = None,
    progress: Callable[[dict], None] | None = None,
    no_cache: bool = False,
) -> AnalysisResult:
    """Run the full ten-phase analysis. Synchronous, with optional progress callback.

    Args:
        results_path: Path to the test results file (relative to workspace OK).
        workspace: Repo root. Defaults to CWD.
        framework: "auto" or one of the framework keys.
        mode: "auto" (scan workspace) or "api-only" (force API_ONLY).
        ask: Callback for clarifying questions. Defaults to non-interactive.
        progress: Callback invoked with phase progress dicts.
    """
    workspace = Path(workspace or Path.cwd()).resolve()
    ask = ask or _no_op_ask
    start = time.monotonic()
    phase_timings: dict = {}

    def emit(event: dict) -> None:
        if progress:
            try:
                progress(event)
            except Exception:
                pass

    # ── Path validation (cheap — resolve before cache check) ──────────────────
    # Inline realpath+join+startswith — the pattern CodeQL's CWE-022 sanitiser
    # recognises. Using os.path functions (strings) keeps the taint chain clean.
    _root = str(workspace)
    _joined = os.path.realpath(os.path.join(_root, str(results_path)))
    if not (_joined == _root or _joined.startswith(_root + os.sep)):
        raise SecurityError("results_path escapes workspace root.")
    if not os.path.isfile(_joined):
        _new = ask("results_path_missing")
        if _new:
            _joined = os.path.realpath(os.path.join(_root, str(_new)))
            if not (_joined == _root or _joined.startswith(_root + os.sep)):
                raise SecurityError("results_path escapes workspace root.")
    if not os.path.isfile(_joined):
        raise FileNotFoundError("Test results file not found.")
    safe_results_path = Path(_joined)

    # ── Framework validation ──────────────────────────────────────────────────
    if framework != "auto":
        from .parsers import FRAMEWORKS
        valid_frameworks = {"auto"} | set(FRAMEWORKS.keys())
        if framework not in valid_frameworks:
            raise ValueError(
                f"Unknown framework: '{framework}'\n"
                f"Supported: {', '.join(sorted(valid_frameworks))}"
            )

    # ── Results file validation ───────────────────────────────────────────────
    _raw = safe_results_path.read_bytes()
    if not _raw.strip():
        raise ValueError(
            f"Results file is empty: {safe_results_path}\n"
            "Run your test suite first to generate a results file."
        )
    _suffix = safe_results_path.suffix.lower()
    if _suffix == ".json":
        import json as _json
        _first_parse_exc = None
        try:
            _json.loads(_raw)
        except _json.JSONDecodeError as exc:
            _first_parse_exc = exc
        if _first_parse_exc is not None:
            # Accept NDJSON (one JSON object per line) — used by `go test -json`.
            _lines = [l for l in _raw.decode("utf-8", errors="replace").splitlines() if l.strip()]
            _ndjson_ok = bool(_lines)
            for _l in _lines[:10]:
                try:
                    _json.loads(_l)
                except _json.JSONDecodeError:
                    _ndjson_ok = False
                    break
            if not _ndjson_ok:
                raise ValueError(
                    f"Results file contains invalid JSON: {safe_results_path}\n"
                    f"  {_first_parse_exc}\n"
                    "Check that your test runner finished successfully and the file is complete."
                ) from _first_parse_exc
    elif _suffix in (".xml", ".trx"):
        _text_start = _raw[:200].lstrip()
        if not (_text_start.startswith(b"<") or _text_start.startswith(b"\xef\xbb\xbf<")):
            raise ValueError(
                f"Results file does not look like valid XML: {safe_results_path}\n"
                "Expected the file to begin with '<'. Check your test runner output."
            )

    # ── Cache check (before Phase 0 so workspace scan is skipped on hit) ─────
    from .cache import CacheKey, load_cached, save_cache
    cache_key = CacheKey.compute(workspace, safe_results_path)
    if not no_cache:
        cached = load_cached(workspace, cache_key)
        if cached is not None:
            emit({"phase": "cache", "name": "Cache hit", "status": "completed"})
            return cached

    # ── Phase 0: Workspace scan ────────────────────────────────────────────────
    emit({"phase": 0, "name": "Scan workspace", "status": "started"})
    profile = scan_workspace(workspace, force_api_only=(mode == "api-only"))
    emit({
        "phase": 0, "name": "Scan workspace", "status": "completed",
        "data": {
            "mode": profile.mode,
            "source_roots": [str(p) for p in profile.source_roots],
            "noise_dirs": len(profile.noise_paths),
        },
    })

    # ── Phase 1: Collect failures ──────────────────────────────────────────
    emit({"phase": 1, "name": "Collect failures", "status": "started"})

    if framework == "auto":
        detected = detect(safe_results_path)
        if detected is None:
            framework = ask("framework_ambiguous") or "playwright"

    detected_fw, failures = parse(safe_results_path, framework=framework)
    emit({
        "phase": 1, "name": "Collect failures", "status": "completed",
        "data": {
            "framework": detected_fw,
            "total": len(failures),
            "failing": sum(1 for f in failures if f.status == "failed"),
            "passing": sum(1 for f in failures if f.status == "passed"),
        },
    })

    # ── Phase 2: Test intent — already in NormalizedFailure (file, line, comments-in-error). No separate call. ─
    emit({"phase": 2, "name": "Read test intent", "status": "completed", "data": {"failures_with_intent": sum(1 for f in failures if f.error_message)}})

    # ── Phase 2.5: Detect flaky tests ─────────────────────────────────────────
    from .intelligence.flaky_detector import detect_flaky
    emit({"phase": "2.5", "name": "Detect flaky tests", "status": "started"})
    _t25 = time.monotonic()
    # history is populated later by FlakyHistoryCollector (Phase 5.5).
    # For now pass None — history-based scoring will be wired after evidence collection.
    failures = detect_flaky(failures, history=None)
    flaky_count = sum(1 for f in failures if (f.flakiness_score or 0) >= 0.5)
    phase_timings["2.5_detect_flaky"] = time.monotonic() - _t25
    emit({
        "phase": "2.5", "name": "Detect flaky tests", "status": "completed",
        "data": {"probable_flakes": flaky_count},
    })

    # ── Phase 5.5: Collect evidence (parallel) ─────────────────────────────
    from .evidence import _REGISTRY
    import time as _time
    emit({"phase": "5.5", "name": "Collect evidence", "status": "started"})
    _t55 = _time.monotonic()
    bundles = _REGISTRY.collect_all(workspace, profile, timeout=30, emit=emit)
    phase_timings["5.5_collect_evidence"] = _time.monotonic() - _t55

    # Extract legacy dicts for backward compat with correlator (unchanged in Phase 1)
    def _legacy(name, fallback):
        b = bundles.get(name)
        return b.legacy if (b and b.legacy) else fallback

    git    = _legacy("git",    {"available": False, "commits": [], "summary": {}})
    logs   = _legacy("logs",   {"available": False, "matches": [], "summary": {}})
    config = _legacy("config", {"available": False, "files":   [], "summary": {}})

    # Wire the no_git_history question to the git bundle result (backward compat)
    if not git.get("available"):
        choice = ask("no_git_history")
        if choice == "no":
            raise RuntimeError("Analysis cancelled — git history requested.")

    # After Phase 5.5, extract history for flaky detector and re-score
    _history_bundle = bundles.get("flaky_history")
    _history_data = (_history_bundle.legacy.get("history") if _history_bundle and _history_bundle.available else None)
    if _history_data is not None:
        failures = detect_flaky(failures, history=_history_data)
        flaky_count = sum(1 for f in failures if (f.flakiness_score or 0) >= 0.5)

    active = [name for name, b in bundles.items() if b.available]
    emit({
        "phase": "5.5", "name": "Collect evidence", "status": "completed",
        "data": {"active_collectors": active, "elapsed_ms": int(phase_timings["5.5_collect_evidence"] * 1000)},
    })

    # ── Phase 6: Correlate ─────────────────────────────────────────────────
    emit({"phase": 6, "name": "Cross-correlate evidence", "status": "started"})
    correlation = correlate(failures, git, logs, config)
    # v2: use Jaccard-distance agglomerative clusterer with EvidenceGraph
    from .intelligence.clusterer import cluster_failures_v2
    from .evidence.graph import EvidenceGraph, EvidenceNode, EvidenceEdge
    evidence_graph = EvidenceGraph()
    # Build graph from legacy git data for backward compat
    for commit in git.get("commits", []):
        cnode = EvidenceNode(
            id=f"commit:{commit['hash']}", type="commit",
            ref=commit["hash"], weight=2.0,
            excerpt=(commit.get("subject") or "")[:200],
        )
        evidence_graph.add_node(cnode)
    # Wire failure→commit edges: link each failure to commits that touch its file
    for failure in failures:
        if not failure.file:
            continue
        for commit in git.get("commits", []):
            changed_files = commit.get("files", []) or []
            if any(failure.file in (cf or "") or (cf or "") in failure.file
                   for cf in changed_files):
                evidence_graph.add_edge(EvidenceEdge(
                    src=failure.id,
                    dst=f"commit:{commit['hash']}",
                    relation="caused_by",
                    weight=2.0,
                ))
    clusters = cluster_failures_v2(failures, evidence_graph)
    emit({
        "phase": 6, "name": "Cross-correlate evidence", "status": "completed",
        "data": {"clusters": len(clusters)},
    })

    # Inject graph and failures into cluster dicts for quality-weighted scorer
    id_to_failure = {f.id: f for f in failures}
    for c in clusters:
        c["_graph"] = evidence_graph
        c["_failures"] = [id_to_failure[i] for i in c["failure_ids"] if i in id_to_failure]

    # ── Phase 7: Form hypotheses ───────────────────────────────────────────
    emit({"phase": 7, "name": "Form hypotheses", "status": "started"})
    hypotheses_raw = form_hypotheses(failures, clusters, correlation["matrix"], git, logs, config)
    hypotheses, suppressed_count, no_app_fault = _filter_hypotheses(hypotheses_raw, profile)
    emit({
        "phase": 7, "name": "Form hypotheses", "status": "completed",
        "data": {
            "count": len(hypotheses),
            "suppressed": suppressed_count,
            "no_app_fault": no_app_fault,
        },
    })

    # ── Phase 8: Render report ─────────────────────────────────────────────
    elapsed = time.monotonic() - start
    emit({"phase": 8, "name": "Produce report", "status": "started"})
    report_md = render_markdown_report(
        failures=failures,
        hypotheses=hypotheses,
        git=git,
        logs=logs,
        config=config,
        framework=detected_fw,
        elapsed_seconds=elapsed,
        profile=profile,
        no_app_fault=no_app_fault,
    )
    emit({"phase": 8, "name": "Produce report", "status": "completed", "data": {"bytes": len(report_md)}})

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

    result = AnalysisResult(
        framework=detected_fw,
        failures=failures,
        git=git,
        logs=logs,
        config=config,
        matrix=correlation["matrix"],
        clusters=clusters,
        hypotheses=hypotheses,
        report_markdown=report_md,
        elapsed_seconds=elapsed,
        profile=profile,
        suppressed_hypotheses=suppressed_count,
        no_app_fault=no_app_fault,
        phase_timings=phase_timings,
    )

    if not no_cache:
        save_cache(workspace, cache_key, result)

    return result
