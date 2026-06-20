# v2 Phase 3 — Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pure-Python ML intelligence: TF-IDF flaky test detection (Phase 2.5), Jaccard-distance agglomerative clustering (Phase 6 upgrade), and quality-weighted confidence scoring (Phase 7 upgrade).

**Architecture:** Three new modules in `analyzer/intelligence/`. Phase 2.5 runs after parse, before evidence collection. The existing correlator is updated to emit an `EvidenceGraph` alongside the legacy matrix (the matrix is kept for one-release compatibility). The existing `form_hypotheses` delegates scoring to `intelligence/scorer.py`.

**Tech Stack:** Python stdlib only — `math`, `collections`, `itertools`. No scikit-learn, no numpy. Research basis: FlaKat (arXiv 2403.01003) for 7-category classification; arXiv 2504.16777 for Jaccard clustering.

## Global Constraints

- Python ≥ 3.10, zero new runtime dependencies
- `flakiness_score` is advisory (0.0–1.0) — it never changes `NormalizedFailure.status`
- `flakiness_category` values: `"ID"` | `"OD"` | `"NOD"` | `"UD"` | `"NDOD"` | `"OD-Vic"` | `"OD-Brit"` | `None`
- Confidence score range: 10–98 (hard-capped, never 0 or 100)
- All intelligence modules must handle empty input without raising
- `pytest tests/analyzer -q` must pass after every task

---

### Task 1: TF-IDF cosine similarity utilities (`analyzer/intelligence/_tfidf.py`)

**Files:**
- Create: `analyzer/intelligence/__init__.py`
- Create: `analyzer/intelligence/_tfidf.py`
- Create: `tests/analyzer/test_intelligence.py`

**Interfaces:**
- Produces:
  - `tokenize(text: str) -> list[str]`
  - `build_tfidf(docs: list[str]) -> list[dict[str, float]]`
  - `cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float`

- [ ] **Step 1: Write failing tests**

Create `tests/analyzer/test_intelligence.py`:

```python
"""Tests for the intelligence layer — flaky detection, clustering, scoring."""
import math
import pytest


# ── TF-IDF utilities ──────────────────────────────────────────────────────────

def test_tokenize_splits_words():
    from analyzer.intelligence._tfidf import tokenize
    tokens = tokenize("Element not found: #login-button")
    assert "element" in tokens
    assert "found" in tokens
    assert "login" in tokens or "button" in tokens  # hyphen split


def test_tokenize_empty_returns_empty():
    from analyzer.intelligence._tfidf import tokenize
    assert tokenize("") == []
    assert tokenize(None) == []


def test_build_tfidf_returns_one_vector_per_doc():
    from analyzer.intelligence._tfidf import build_tfidf
    docs = ["timeout error occurred", "element not found timeout"]
    vecs = build_tfidf(docs)
    assert len(vecs) == 2
    # "timeout" appears in both docs — should have lower IDF weight than unique terms
    assert "timeout" in vecs[0]


def test_build_tfidf_empty_docs():
    from analyzer.intelligence._tfidf import build_tfidf
    assert build_tfidf([]) == []
    assert build_tfidf([""]) == [{}]


def test_cosine_similarity_identical_vectors():
    from analyzer.intelligence._tfidf import cosine_similarity
    v = {"a": 1.0, "b": 2.0}
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal_vectors():
    from analyzer.intelligence._tfidf import cosine_similarity
    v1 = {"a": 1.0}
    v2 = {"b": 1.0}
    assert cosine_similarity(v1, v2) == 0.0


def test_cosine_similarity_empty_vector():
    from analyzer.intelligence._tfidf import cosine_similarity
    assert cosine_similarity({}, {"a": 1.0}) == 0.0
    assert cosine_similarity({}, {}) == 0.0


def test_similar_error_messages_have_high_cosine_similarity():
    from analyzer.intelligence._tfidf import build_tfidf, cosine_similarity
    docs = [
        "Expected status 201 but got 404 for POST /api/users",
        "Expected status 201 but received 404 for POST /api/users/register",
        "Completely unrelated database connection refused",
    ]
    vecs = build_tfidf(docs)
    sim_similar = cosine_similarity(vecs[0], vecs[1])
    sim_different = cosine_similarity(vecs[0], vecs[2])
    assert sim_similar > sim_different
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_intelligence.py::test_tokenize_splits_words -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/intelligence/__init__.py`**

```python
"""Pure-Python intelligence layer — flaky detection, clustering, confidence scoring."""
```

- [ ] **Step 4: Create `analyzer/intelligence/_tfidf.py`**

```python
"""TF-IDF cosine similarity — pure Python stdlib, no numpy/scikit-learn."""
from __future__ import annotations
import math
import re
from collections import Counter


def tokenize(text: str | None) -> list[str]:
    """Lowercase, split on non-alphanumeric, filter stopwords and short tokens."""
    if not text:
        return []
    _STOPWORDS = {"the", "and", "for", "not", "but", "are", "was", "with",
                  "this", "that", "from", "have", "has", "had", "its", "been"}
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def build_tfidf(docs: list[str]) -> list[dict[str, float]]:
    """Build TF-IDF vectors for a list of documents.

    Returns one dict per document mapping term → TF-IDF weight.
    """
    if not docs:
        return []

    tokenized = [tokenize(d) for d in docs]
    n = len(tokenized)

    # Document frequency: how many docs contain each term
    df: dict[str, int] = {}
    for tokens in tokenized:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1

    vectors: list[dict[str, float]] = []
    for tokens in tokenized:
        if not tokens:
            vectors.append({})
            continue
        tf = Counter(tokens)
        total = len(tokens)
        vec: dict[str, float] = {}
        for term, count in tf.items():
            tf_val = count / total
            idf_val = math.log((n + 1) / (df.get(term, 0) + 1)) + 1.0
            vec[term] = tf_val * idf_val
        vectors.append(vec)
    return vectors


def cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
    """Cosine similarity between two TF-IDF vectors (0.0–1.0)."""
    if not v1 or not v2:
        return 0.0
    shared = set(v1) & set(v2)
    if not shared:
        return 0.0
    dot = sum(v1[t] * v2[t] for t in shared)
    mag1 = math.sqrt(sum(x * x for x in v1.values()))
    mag2 = math.sqrt(sum(x * x for x in v2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)
```

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_intelligence.py -v -k "tfidf or tokenize or cosine or similarity"
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add analyzer/intelligence/__init__.py analyzer/intelligence/_tfidf.py tests/analyzer/test_intelligence.py
git commit -m "feat(v2): add pure-Python TF-IDF cosine similarity utilities"
```

---

### Task 2: Flaky test detector — Phase 2.5 (`analyzer/intelligence/flaky_detector.py`)

**Files:**
- Create: `analyzer/intelligence/flaky_detector.py`
- Modify: `tests/analyzer/test_intelligence.py`

**Interfaces:**
- Consumes: `NormalizedFailure` from `analyzer.parsers.base`; `build_tfidf`, `cosine_similarity` from `analyzer.intelligence._tfidf`
- Produces: `detect_flaky(failures: list[NormalizedFailure], history: dict | None) -> list[NormalizedFailure]` — annotates in-place, returns same list

- [ ] **Step 1: Write failing tests**

Add to `tests/analyzer/test_intelligence.py`:

```python
# ── Flaky detector ────────────────────────────────────────────────────────────

def _make_failure(title, error_msg=None, status="failed"):
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    return NormalizedFailure(
        id=make_failure_id("pytest", "suite", title, "test.py"),
        framework="pytest", suite="suite", title=title, file="test.py",
        status=status, error_message=error_msg,
    )


def test_flaky_detector_returns_same_list():
    from analyzer.intelligence.flaky_detector import detect_flaky
    failures = [_make_failure("test_a", "timeout after 5s")]
    result = detect_flaky(failures, history=None)
    assert result is failures  # mutates in-place, returns same object


def test_flaky_detector_does_not_change_status():
    from analyzer.intelligence.flaky_detector import detect_flaky
    failures = [_make_failure("test_a", "timeout after 5s")]
    detect_flaky(failures, history=None)
    assert failures[0].status == "failed"  # status must NOT be changed


def test_flaky_detector_empty_input():
    from analyzer.intelligence.flaky_detector import detect_flaky
    result = detect_flaky([], history=None)
    assert result == []


def test_flaky_detector_timeout_error_scores_id_category():
    from analyzer.intelligence.flaky_detector import detect_flaky
    failures = [_make_failure("test_slow", "Timeout: element not found after 30000ms")]
    detect_flaky(failures, history=None)
    assert failures[0].flakiness_category == "ID"
    assert (failures[0].flakiness_score or 0) > 0


def test_flaky_detector_network_error_scores_ud_category():
    from analyzer.intelligence.flaky_detector import detect_flaky
    failures = [_make_failure("test_api", "ECONNREFUSED 127.0.0.1:3000")]
    detect_flaky(failures, history=None)
    assert failures[0].flakiness_category == "UD"


def test_flaky_detector_similar_errors_increase_score():
    from analyzer.intelligence.flaky_detector import detect_flaky
    # Two tests with very similar error messages should each get a higher score
    # than a single isolated test with the same message
    isolated = [_make_failure("test_isolated", "Expected status 201 but got 404")]
    similar_pair = [
        _make_failure("test_a", "Expected status 201 but got 404 for POST /users"),
        _make_failure("test_b", "Expected status 201 but got 404 for POST /users/register"),
    ]
    detect_flaky(isolated, history=None)
    detect_flaky(similar_pair, history=None)
    # Similar pair tests should have higher score due to TF-IDF signal
    avg_pair = sum(f.flakiness_score or 0 for f in similar_pair) / 2
    assert avg_pair >= (isolated[0].flakiness_score or 0)


def test_flaky_detector_order_dependent_error_scores_od():
    from analyzer.intelligence.flaky_detector import detect_flaky
    failures = [_make_failure("test_setup", "duplicate key constraint in beforeAll setup")]
    detect_flaky(failures, history=None)
    assert failures[0].flakiness_category in ("OD", "OD-Vic")


def test_flaky_detector_history_increases_score():
    from analyzer.intelligence.flaky_detector import detect_flaky
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    fid = make_failure_id("pytest", "suite", "test_intermittent", "test.py")
    failure = NormalizedFailure(
        id=fid, framework="pytest", suite="suite",
        title="test_intermittent", file="test.py", status="failed",
    )
    # History: this test failed in run1 but NOT run2 and run3 (intermittent)
    history = {
        "runs": [
            {"run_id": "run1", "failures": [{"id": fid, "status": "failed"}]},
            {"run_id": "run2", "failures": []},
            {"run_id": "run3", "failures": []},
        ]
    }
    detect_flaky([failure], history=history)
    assert (failure.flakiness_score or 0) > 0
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_intelligence.py::test_flaky_detector_returns_same_list -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/intelligence/flaky_detector.py`**

```python
"""Phase 2.5 — Flaky test detection using TF-IDF + FlaKat categories + Jaccard history.

Research basis:
  FlaKat (arXiv 2403.01003): 7-category classifier, F1=0.67 on IDoFT dataset.
  arXiv 2504.16777: Jaccard distance on run-sets for co-flaky grouping.
"""
from __future__ import annotations
from analyzer.parsers.base import NormalizedFailure
from ._tfidf import build_tfidf, cosine_similarity

# FlaKat 7-category keyword signals
_CATEGORY_SIGNALS: dict[str, list[str]] = {
    "ID": ["timeout", "timed out", "stale element", "detached", "intercept",
           "element not found", "no such element", "element not visible",
           "waitfor", "waituntil"],
    "OD": ["already exists", "duplicate key", "unique constraint",
           "beforeall", "aftereach", "setup", "teardown", "test order"],
    "OD-Vic": ["setup failed", "beforeall failed", "fixture setup"],
    "OD-Brit": ["teardown failed", "afterall failed", "fixture teardown"],
    "NOD": ["random", "concurrent", "race condition", "deadlock", "async",
            "nondeterministic", "non-deterministic", "parallel"],
    "UD": ["econnrefused", "enotfound", "network", "dns", "socket hang up",
           "fetch failed", "connect etimedout", "connection refused"],
    "NDOD": ["flaky", "intermittent", "sometimes fails", "occasionally"],
}

_COSINE_THRESHOLD = 0.85
_SCORE_CAP = 1.0


def _classify_category(text: str | None) -> str | None:
    if not text:
        return None
    lower = text.lower()
    scores: dict[str, int] = {}
    for cat, signals in _CATEGORY_SIGNALS.items():
        hits = sum(1 for s in signals if s in lower)
        if hits:
            scores[cat] = hits
    if not scores:
        return None
    # NDOD takes priority if "flaky" literal present
    if "NDOD" in scores:
        return "NDOD"
    return max(scores, key=scores.__getitem__)


def _jaccard_distance(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0.0
    return 1.0 - len(set_a & set_b) / len(set_a | set_b)


def _history_flakiness(failure_id: str, history: dict) -> float:
    """Score 0.0–0.3 based on intermittent appearance in run history."""
    runs = history.get("runs", [])
    if len(runs) < 2:
        return 0.0
    run_ids_with_failure = {
        r["run_id"] for r in runs
        if any(f["id"] == failure_id for f in r.get("failures", []))
    }
    run_ids_without = {r["run_id"] for r in runs} - run_ids_with_failure
    if not run_ids_with_failure or not run_ids_without:
        return 0.0
    # High Jaccard distance between "in" and "out" sets → intermittent → flaky
    dist = _jaccard_distance(run_ids_with_failure, run_ids_without)
    return min(dist * 0.3, 0.3)


def detect_flaky(
    failures: list[NormalizedFailure],
    history: dict | None,
) -> list[NormalizedFailure]:
    """Annotate failures with flakiness_score and flakiness_category in-place.

    Never changes failure.status — scores are advisory only.
    Returns the same list object (mutation in-place).
    """
    if not failures:
        return failures

    # Signal 1: TF-IDF cosine similarity between error messages
    error_texts = [(f.error_message or f.title or "") for f in failures]
    tfidf_vecs = build_tfidf(error_texts)
    similarity_scores: list[float] = [0.0] * len(failures)
    for i in range(len(failures)):
        for j in range(i + 1, len(failures)):
            sim = cosine_similarity(tfidf_vecs[i], tfidf_vecs[j])
            if sim >= _COSINE_THRESHOLD:
                # Each test in the similar pair gets a boost
                similarity_scores[i] = min(similarity_scores[i] + 0.3, 0.6)
                similarity_scores[j] = min(similarity_scores[j] + 0.3, 0.6)

    for i, failure in enumerate(failures):
        score = 0.0

        # Signal 1: TF-IDF similarity boost
        score += similarity_scores[i]

        # Signal 2: FlaKat category classification
        blob = " ".join(filter(None, (failure.error_message, failure.error_stack, failure.title)))
        category = _classify_category(blob)
        if category:
            failure.flakiness_category = category
            # Count matched signals for this category
            lower = blob.lower()
            matched = sum(1 for s in _CATEGORY_SIGNALS.get(category, []) if s in lower)
            score += min(matched * 0.1, 0.4)

        # Signal 3: Jaccard run-history distance
        if history:
            score += _history_flakiness(failure.id, history)

        failure.flakiness_score = min(score, _SCORE_CAP)

    return failures
```

- [ ] **Step 4: Run tests**

```
pytest tests/analyzer/test_intelligence.py -v -k "flaky"
```
Expected: all pass.

- [ ] **Step 5: Wire Phase 2.5 into orchestrator**

In `analyzer/orchestrator.py`, find the Phase 2 emit block. After it, add:

```python
    # ── Phase 2.5: Detect flaky tests ─────────────────────────────────────────
    from .intelligence.flaky_detector import detect_flaky
    emit({"phase": "2.5", "name": "Detect flaky tests", "status": "started"})
    _t25 = time.monotonic()
    # history is populated later by FlakyHistoryCollector (Phase 4 plan).
    # For now pass None — history-based scoring activates in Phase 4.
    failures = detect_flaky(failures, history=None)
    flaky_count = sum(1 for f in failures if (f.flakiness_score or 0) >= 0.5)
    phase_timings["2.5_detect_flaky"] = time.monotonic() - _t25
    emit({
        "phase": "2.5", "name": "Detect flaky tests", "status": "completed",
        "data": {"probable_flakes": flaky_count},
    })
```

- [ ] **Step 6: Run full suite**

```
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add analyzer/intelligence/flaky_detector.py tests/analyzer/test_intelligence.py analyzer/orchestrator.py
git commit -m "feat(v2): add flaky detector Phase 2.5 — TF-IDF + FlaKat 7-category classification"
```

---

### Task 3: Jaccard-distance agglomerative clusterer (`analyzer/intelligence/clusterer.py`)

**Files:**
- Create: `analyzer/intelligence/clusterer.py`
- Modify: `tests/analyzer/test_intelligence.py`
- Modify: `analyzer/evidence/correlator.py`

**Interfaces:**
- Consumes: `NormalizedFailure`, `EvidenceGraph` from `analyzer.evidence.graph`, `cosine_similarity` from `analyzer.intelligence._tfidf`
- Produces: `cluster_failures_v2(failures, graph) -> list[dict]` — same cluster dict shape as existing `cluster_failures()` for drop-in compatibility

- [ ] **Step 1: Write failing tests**

Add to `tests/analyzer/test_intelligence.py`:

```python
# ── Clusterer ─────────────────────────────────────────────────────────────────

def test_clusterer_groups_shared_commit():
    """Two failures sharing a git commit must end up in the same cluster."""
    from analyzer.intelligence.clusterer import cluster_failures_v2
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    from analyzer.evidence.graph import EvidenceGraph, EvidenceEdge, EvidenceNode

    def _f(title):
        fid = make_failure_id("pytest", "suite", title, "test.py")
        return NormalizedFailure(id=fid, framework="pytest", suite="suite",
                                 title=title, file="test.py", status="failed")

    fa, fb = _f("test_a"), _f("test_b")
    g = EvidenceGraph()
    commit_node = EvidenceNode(id="commit:abc", type="commit", ref="abc", weight=2.0, excerpt="")
    g.add_node(commit_node)
    g.add_node(EvidenceNode(id=fa.id, type="failure", ref=fa.file, weight=0.0, excerpt=""))
    g.add_node(EvidenceNode(id=fb.id, type="failure", ref=fb.file, weight=0.0, excerpt=""))
    g.add_edge(EvidenceEdge(src=fa.id, dst="commit:abc", relation="caused_by", weight=2.0))
    g.add_edge(EvidenceEdge(src=fb.id, dst="commit:abc", relation="caused_by", weight=2.0))

    clusters = cluster_failures_v2([fa, fb], g)
    # Both failures share a commit → should be in same cluster
    all_ids = [fid for c in clusters for fid in c["failure_ids"]]
    assert fa.id in all_ids
    assert fb.id in all_ids
    assert len(clusters) == 1 or any(
        fa.id in c["failure_ids"] and fb.id in c["failure_ids"] for c in clusters
    )


def test_clusterer_separates_unrelated_failures():
    """Two completely unrelated failures must be in different clusters."""
    from analyzer.intelligence.clusterer import cluster_failures_v2
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    from analyzer.evidence.graph import EvidenceGraph

    def _f(title, error):
        fid = make_failure_id("pytest", "suite", title, "test.py")
        return NormalizedFailure(id=fid, framework="pytest", suite="suite",
                                 title=title, file="test.py", status="failed",
                                 error_message=error, http={"status_got": None, "status_expected": None, "method": None, "url": None})

    fa = _f("test_auth", "401 unauthorized token expired")
    fb = _f("test_db", "database connection timeout after 30s")
    clusters = cluster_failures_v2([fa, fb], EvidenceGraph())
    assert len(clusters) == 2


def test_clusterer_returns_required_keys():
    """Each cluster dict must have cluster_id, failure_ids, size keys."""
    from analyzer.intelligence.clusterer import cluster_failures_v2
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    from analyzer.evidence.graph import EvidenceGraph

    fid = make_failure_id("pytest", "suite", "test_x", "test.py")
    f = NormalizedFailure(id=fid, framework="pytest", suite="suite",
                          title="test_x", file="test.py", status="failed")
    clusters = cluster_failures_v2([f], EvidenceGraph())
    assert len(clusters) == 1
    assert "cluster_id" in clusters[0]
    assert "failure_ids" in clusters[0]
    assert "size" in clusters[0]
    assert clusters[0]["size"] == 1


def test_clusterer_empty_input():
    from analyzer.intelligence.clusterer import cluster_failures_v2
    from analyzer.evidence.graph import EvidenceGraph
    assert cluster_failures_v2([], EvidenceGraph()) == []
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_intelligence.py::test_clusterer_groups_shared_commit -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/intelligence/clusterer.py`**

```python
"""Jaccard-distance agglomerative clusterer for failure grouping.

Replaces the signature-tuple grouping in evidence/correlator.py.
Research basis: arXiv 2504.16777 — agglomerative clustering on Jaccard distance
between failure run-sets; silhouette threshold 0.6 for automated grouping.
"""
from __future__ import annotations
from analyzer.parsers.base import NormalizedFailure
from analyzer.evidence.graph import EvidenceGraph, EvidenceEdge
from ._tfidf import cosine_similarity, build_tfidf

_MERGE_THRESHOLD = 0.4   # distance ≤ this → same cluster
_MAX_FAILURES = 300       # hard cap to keep O(n²) manageable


def _commit_ids(graph: EvidenceGraph, failure_id: str) -> set[str]:
    """Return the set of commit node IDs linked from a failure via caused_by edges."""
    return {
        e.dst for e in graph.edges
        if e.src == failure_id and e.relation == "caused_by"
           and graph.nodes.get(e.dst) and graph.nodes[e.dst].type == "commit"
    }


def _http_status_class(failure: NormalizedFailure) -> int | None:
    if failure.http and isinstance(failure.http.get("status_got"), int):
        return failure.http["status_got"] // 100
    return None


def _failure_distance(
    a: NormalizedFailure,
    b: NormalizedFailure,
    graph: EvidenceGraph,
    sim_cache: dict[tuple[str, str], float],
) -> float:
    """Composite distance between two failures. 0.0 = same root cause, 1.0 = unrelated."""
    d = 1.0

    # Shared git commit → strong link (-0.4)
    commits_a = _commit_ids(graph, a.id)
    commits_b = _commit_ids(graph, b.id)
    if commits_a and commits_b and (commits_a & commits_b):
        d -= 0.4

    # Same HTTP status class → moderate link (-0.2)
    sc_a, sc_b = _http_status_class(a), _http_status_class(b)
    if sc_a is not None and sc_a == sc_b:
        d -= 0.2

    # High error-message cosine similarity → moderate link (-0.2)
    cache_key = (min(a.id, b.id), max(a.id, b.id))
    sim = sim_cache.get(cache_key, -1.0)
    if sim >= 0.85:
        d -= 0.2

    # Same flakiness category → weak link (-0.1)
    if a.flakiness_category and a.flakiness_category == b.flakiness_category:
        d -= 0.1

    return max(0.0, d)


def cluster_failures_v2(
    failures: list[NormalizedFailure],
    graph: EvidenceGraph,
) -> list[dict]:
    """Agglomerative clustering on composite Jaccard distance.

    Returns list of cluster dicts with keys:
      cluster_id, failure_ids, failure_titles, shared_commits,
      shared_risk_flags, endpoints, size.
    """
    only_failed = [f for f in failures if f.status in ("failed", "flaky")]
    if not only_failed:
        return []

    # Hard cap: prevent O(n²) blowup on pathological inputs
    if len(only_failed) > _MAX_FAILURES:
        only_failed = only_failed[:_MAX_FAILURES]

    n = len(only_failed)

    # Pre-compute TF-IDF similarity cache to avoid re-computing inside distance function
    error_texts = [(f.error_message or f.title or "") for f in only_failed]
    tfidf_vecs = build_tfidf(error_texts)
    sim_cache: dict[tuple[str, str], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            sim = cosine_similarity(tfidf_vecs[i], tfidf_vecs[j])
            key = (min(only_failed[i].id, only_failed[j].id),
                   max(only_failed[i].id, only_failed[j].id))
            sim_cache[key] = sim

    # Start: each failure is its own cluster
    cluster_members: list[list[int]] = [[i] for i in range(n)]

    def _cluster_distance(c1: list[int], c2: list[int]) -> float:
        """Average linkage between two clusters."""
        pairs = [(only_failed[i], only_failed[j]) for i in c1 for j in c2]
        if not pairs:
            return 1.0
        return sum(_failure_distance(a, b, graph, sim_cache) for a, b in pairs) / len(pairs)

    # Agglomerative merge: find closest pair below threshold, merge, repeat
    changed = True
    while changed and len(cluster_members) > 1:
        changed = False
        best_dist = _MERGE_THRESHOLD
        best_pair = (-1, -1)
        for i in range(len(cluster_members)):
            for j in range(i + 1, len(cluster_members)):
                d = _cluster_distance(cluster_members[i], cluster_members[j])
                if d < best_dist:
                    best_dist = d
                    best_pair = (i, j)
        if best_pair[0] >= 0:
            i, j = best_pair
            cluster_members[i].extend(cluster_members[j])
            cluster_members.pop(j)
            changed = True

    # Build output dicts matching the shape expected by form_hypotheses
    out = []
    for idx, members in enumerate(cluster_members, start=1):
        cluster_failures = [only_failed[m] for m in members]
        fids = [f.id for f in cluster_failures]
        shared_commits = sorted({
            e.dst for f in cluster_failures
            for e in graph.edges
            if e.src == f.id and e.relation == "caused_by"
        })
        endpoints = sorted({
            (f.http.get("url") or "") for f in cluster_failures
            if f.http and f.http.get("url")
        })
        out.append({
            "cluster_id": f"C{idx}",
            "failure_ids": fids,
            "failure_titles": [f.title for f in cluster_failures],
            "shared_commits": shared_commits,
            "shared_risk_flags": [],  # populated by correlator in Phase 4 plan
            "endpoints": list(filter(None, endpoints)),
            "size": len(fids),
        })

    out.sort(key=lambda c: c["size"], reverse=True)
    return out
```

- [ ] **Step 4: Wire into correlator**

In `analyzer/evidence/correlator.py`, at the top of `correlate()`, add the import and call:

```python
from ..intelligence.clusterer import cluster_failures_v2
```

In `cluster_failures()` — DO NOT replace it yet. Add a new function `cluster_failures_v2_wrapper` that delegates to the new module:

Actually, the simplest wiring: in `analyzer/orchestrator.py`, where it calls `cluster_failures(failures, correlation["matrix"])`, add an import and replace with the v2 clusterer:

```python
    # ── Phase 6: Correlate ──────────────────────────────────────────────────
    emit({"phase": 6, "name": "Cross-correlate evidence", "status": "started"})
    correlation = correlate(failures, git, logs, config)
    # v2: use Jaccard-distance agglomerative clusterer with EvidenceGraph
    from .intelligence.clusterer import cluster_failures_v2
    from .evidence.graph import EvidenceGraph
    evidence_graph = EvidenceGraph()  # will be populated by collectors in Phase 4
    # For now, build graph from legacy git data for backward compat
    for commit in git.get("commits", []):
        from .evidence.graph import EvidenceNode, EvidenceEdge
        cnode = EvidenceNode(
            id=f"commit:{commit['hash']}", type="commit",
            ref=commit["hash"], weight=2.0,
            excerpt=(commit.get("subject") or "")[:200],
        )
        evidence_graph.add_node(cnode)
    clusters = cluster_failures_v2(failures, evidence_graph)
    emit({
        "phase": 6, "name": "Cross-correlate evidence", "status": "completed",
        "data": {"clusters": len(clusters)},
    })
```

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_intelligence.py -v -k "clusterer or cluster"
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add analyzer/intelligence/clusterer.py tests/analyzer/test_intelligence.py analyzer/orchestrator.py
git commit -m "feat(v2): add Jaccard-distance agglomerative clusterer, wire as Phase 6"
```

---

### Task 4: Quality-weighted confidence scorer (`analyzer/intelligence/scorer.py`)

**Files:**
- Create: `analyzer/intelligence/scorer.py`
- Modify: `analyzer/hypothesis.py`
- Modify: `tests/analyzer/test_intelligence.py`

**Interfaces:**
- Consumes: `EvidenceGraph`, `Hypothesis`, `NormalizedFailure`
- Produces: `score_cluster(cluster_id, cluster_failure_ids, graph, failures) -> tuple[int, str]` — returns `(confidence_0_to_98, justification_string)`

- [ ] **Step 1: Write failing tests**

Add to `tests/analyzer/test_intelligence.py`:

```python
# ── Scorer ────────────────────────────────────────────────────────────────────

def test_scorer_single_source_capped_at_55():
    """With only test output (no Tier-1 evidence), score must be ≤ 55."""
    from analyzer.intelligence.scorer import score_cluster
    from analyzer.evidence.graph import EvidenceGraph
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    fid = make_failure_id("pytest", "s", "t", "f.py")
    f = NormalizedFailure(id=fid, framework="pytest", suite="s", title="t", file="f.py",
                          status="failed")
    score, justification = score_cluster("C1", [fid], EvidenceGraph(), [f])
    assert score <= 55
    assert isinstance(justification, str)


def test_scorer_tier1_evidence_increases_score():
    """Adding a Tier-1 commit node must increase score above single-source cap."""
    from analyzer.intelligence.scorer import score_cluster
    from analyzer.evidence.graph import EvidenceGraph, EvidenceNode, EvidenceEdge
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    fid = make_failure_id("pytest", "s", "t", "f.py")
    f = NormalizedFailure(id=fid, framework="pytest", suite="s", title="t", file="f.py",
                          status="failed")
    g = EvidenceGraph()
    g.add_node(EvidenceNode(id=fid, type="failure", ref="f.py", weight=0.0, excerpt=""))
    g.add_node(EvidenceNode(id="commit:abc", type="commit", ref="abc", weight=2.0, excerpt="rename"))
    g.add_node(EvidenceNode(id="log:0", type="log_line", ref="app.log:42", weight=2.0, excerpt="ERROR"))
    g.add_edge(EvidenceEdge(src=fid, dst="commit:abc", relation="caused_by", weight=2.0))
    g.add_edge(EvidenceEdge(src=fid, dst="log:0", relation="related_to", weight=2.0))
    score, _ = score_cluster("C1", [fid], g, [f])
    assert score > 55


def test_scorer_flaky_test_penalises_score():
    """A probable flake must reduce confidence."""
    from analyzer.intelligence.scorer import score_cluster
    from analyzer.evidence.graph import EvidenceGraph, EvidenceNode, EvidenceEdge
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    fid = make_failure_id("pytest", "s", "t", "f.py")
    f_normal = NormalizedFailure(id=fid, framework="pytest", suite="s", title="t",
                                 file="f.py", status="failed", flakiness_score=0.0)
    f_flaky  = NormalizedFailure(id=fid, framework="pytest", suite="s", title="t",
                                 file="f.py", status="failed", flakiness_score=0.9)
    g = EvidenceGraph()
    g.add_node(EvidenceNode(id=fid, type="failure", ref="f.py", weight=0.0, excerpt=""))
    g.add_node(EvidenceNode(id="commit:abc", type="commit", ref="abc", weight=2.0, excerpt=""))
    g.add_edge(EvidenceEdge(src=fid, dst="commit:abc", relation="caused_by", weight=2.0))
    score_normal, _ = score_cluster("C1", [fid], g, [f_normal])
    score_flaky, _  = score_cluster("C1", [fid], g, [f_flaky])
    assert score_flaky < score_normal


def test_scorer_score_always_in_valid_range():
    """Score must always be between 10 and 98 inclusive."""
    from analyzer.intelligence.scorer import score_cluster
    from analyzer.evidence.graph import EvidenceGraph
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    fid = make_failure_id("pytest", "s", "t", "f.py")
    f = NormalizedFailure(id=fid, framework="pytest", suite="s", title="t",
                          file="f.py", status="failed", flakiness_score=1.0)
    score, _ = score_cluster("C1", [fid], EvidenceGraph(), [f])
    assert 10 <= score <= 98
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/analyzer/test_intelligence.py::test_scorer_single_source_capped_at_55 -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 3: Create `analyzer/intelligence/scorer.py`**

```python
"""Quality-weighted confidence scorer for hypothesis formation.

Replaces the source-count formula in analyzer/hypothesis.py.
Quality weighting: Tier-1 evidence (weight=2.0) contributes more than
Tier-2 (weight=1.0). Flaky tests penalise confidence. Contradicting
evidence reduces score. Hard caps based on evidence quality.
"""
from __future__ import annotations
from analyzer.evidence.graph import EvidenceGraph
from analyzer.parsers.base import NormalizedFailure


def score_cluster(
    cluster_id: str,
    cluster_failure_ids: list[str],
    graph: EvidenceGraph,
    failures: list[NormalizedFailure],
) -> tuple[int, str]:
    """Compute quality-weighted confidence score for a cluster.

    Returns (score_10_to_98, justification_string).
    """
    fid_set = set(cluster_failure_ids)

    # Gather all evidence nodes linked to this cluster
    linked_node_ids: set[str] = set()
    for e in graph.edges:
        if e.src in fid_set:
            linked_node_ids.add(e.dst)

    linked_nodes = [graph.nodes[nid] for nid in linked_node_ids if nid in graph.nodes]
    source_types = {n.type for n in linked_nodes}

    # Base: sum of edge weights from cluster failures to evidence nodes
    raw_weight = sum(
        e.weight for e in graph.edges
        if e.src in fid_set and e.dst in linked_node_ids
    )

    # Corroboration bonus: +5 per independent source type, max +20
    corroboration = min(len(source_types) * 5, 20)

    # Tier-1 count: nodes with weight >= 2.0
    tier1_count = sum(1 for n in linked_nodes if n.weight >= 2.0)

    # Flaky penalty: -8 per probable flake (flakiness_score >= 0.5), max -20
    cluster_failures = [f for f in failures if f.id in fid_set]
    flaky_count = sum(1 for f in cluster_failures if (f.flakiness_score or 0.0) >= 0.5)
    flaky_penalty = min(flaky_count * 8, 20)

    # Contradiction penalty: -15 per contradicting edge
    contradiction_count = sum(
        1 for e in graph.edges
        if e.src in fid_set and e.relation == "contradicts"
    )
    contradiction_penalty = contradiction_count * 15

    raw = int(raw_weight * 15) + corroboration - flaky_penalty - contradiction_penalty

    # Hard caps
    if tier1_count == 0 and not source_types:
        # Single test output only
        raw = min(raw, 55)
    if tier1_count == 0 and source_types:
        raw = min(raw, 40)

    score = max(10, min(98, raw))

    # Build justification string
    parts = []
    if source_types:
        parts.append(f"evidence: {'+'.join(sorted(source_types))}")
    if tier1_count:
        parts.append(f"{tier1_count} Tier-1 source(s)")
    if flaky_count:
        parts.append(f"{flaky_count} probable flake(s) penalised")
    if contradiction_count:
        parts.append(f"{contradiction_count} contradiction(s) penalised")
    justification = " · ".join(parts) if parts else "test output only"

    return score, justification
```

- [ ] **Step 4: Wire scorer into `analyzer/hypothesis.py`**

In `analyzer/hypothesis.py`, find the `_score()` function. Replace its body with:

```python
def _score(cluster: dict, has_git: bool, has_logs: bool, has_config: bool) -> tuple[int, str]:
    """Delegates to quality-weighted scorer when graph is available.
    Falls back to legacy source-count formula for backward compat."""
    # The graph is passed via cluster["_graph"] if set by orchestrator (v2 path).
    # Without it, use legacy formula.
    graph = cluster.get("_graph")
    failures = cluster.get("_failures", [])
    failure_ids = cluster.get("failure_ids", [])
    if graph is not None:
        from .intelligence.scorer import score_cluster
        return score_cluster(cluster.get("cluster_id", "C?"), failure_ids, graph, failures)
    # Legacy path (v1 behavior)
    sources = 1
    notes = ["test output observed"]
    if cluster.get("shared_commits") and has_git:
        sources += 1
        notes.append(f"{len(cluster['shared_commits'])} related commit(s)")
    if cluster.get("shared_risk_flags"):
        sources += 1
        notes.append(f"risk flags: {', '.join(cluster['shared_risk_flags'])}")
    if has_logs:
        sources += 1
        notes.append("log evidence available")
    if has_config:
        sources += 1
        notes.append("config evidence available")
    if sources >= 4:
        score = 90 + min(sources - 4, 8)
    elif sources == 3:
        score = 75
    elif sources == 2:
        score = 60
    else:
        score = 45 if cluster.get("size", 0) >= 2 else 35
    return score, " · ".join(notes)
```

In `analyzer/orchestrator.py`, after building `evidence_graph` in Phase 6, pass it and failures into clusters:

```python
    # Inject graph and failures into cluster dicts for scorer
    id_to_failure = {f.id: f for f in failures}
    for c in clusters:
        c["_graph"] = evidence_graph
        c["_failures"] = [id_to_failure[i] for i in c["failure_ids"] if i in id_to_failure]
```

- [ ] **Step 5: Run tests**

```
pytest tests/analyzer/test_intelligence.py -v -k "scorer or score"
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add analyzer/intelligence/scorer.py tests/analyzer/test_intelligence.py analyzer/hypothesis.py analyzer/orchestrator.py
git commit -m "feat(v2): add quality-weighted confidence scorer, wire into hypothesis formation"
```

---

## Phase 3 Complete

At this point:
- `analyzer/intelligence/` has `_tfidf.py`, `flaky_detector.py`, `clusterer.py`, `scorer.py`
- Phase 2.5 annotates failures with `flakiness_score` and `flakiness_category`
- Phase 6 uses Jaccard-distance agglomerative clustering
- Phase 7 uses quality-weighted confidence scoring with flaky penalties
- All existing tests pass

**Next:** Phase 4 — New Collectors + CTRF Output + Caching + Delivery
