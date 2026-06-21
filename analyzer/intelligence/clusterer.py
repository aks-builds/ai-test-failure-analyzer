"""Jaccard-distance agglomerative clusterer for failure grouping.

Replaces the signature-tuple grouping in evidence/correlator.py.
Research basis: arXiv 2504.16777 — agglomerative clustering on Jaccard distance
between failure run-sets; silhouette threshold 0.6 for automated grouping.
"""
from __future__ import annotations
import warnings
from analyzer.parsers.base import NormalizedFailure
from analyzer.evidence.graph import EvidenceGraph
from ._tfidf import cosine_similarity, build_tfidf

_MERGE_THRESHOLD = 0.5    # distance ≤ this → same cluster
_MAX_FAILURES = 300        # hard cap to keep O(n²) manageable
_SILHOUETTE_THRESHOLD = 0.6  # fall back to singletons if avg silhouette < this


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

    # High error-message cosine similarity → moderate/strong link
    cache_key = (min(a.id, b.id), max(a.id, b.id))
    sim = sim_cache.get(cache_key, -1.0)
    if sim >= 0.90:
        d -= 0.35
    elif sim >= 0.85:
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
        warnings.warn(
            f"cluster_failures_v2: {len(only_failed)} failures exceeds cap of {_MAX_FAILURES}; "
            f"truncating to first {_MAX_FAILURES}",
            RuntimeWarning,
            stacklevel=2,
        )
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

    # Agglomerative merge: find closest pair at or below threshold, merge, repeat
    changed = True
    while changed and len(cluster_members) > 1:
        changed = False
        best_dist = _MERGE_THRESHOLD + 1.0  # sentinel above any real distance
        best_pair = (-1, -1)
        for i in range(len(cluster_members)):
            for j in range(i + 1, len(cluster_members)):
                d = _cluster_distance(cluster_members[i], cluster_members[j])
                if d <= _MERGE_THRESHOLD and d < best_dist:
                    best_dist = d
                    best_pair = (i, j)
        if best_pair[0] >= 0:
            i, j = best_pair
            cluster_members[i].extend(cluster_members[j])
            cluster_members.pop(j)
            changed = True

    # Silhouette check: fall back to singleton clusters if quality is poor
    if len(cluster_members) > 1:
        # Build an index from failure id pair to distance for quick lookup
        def _point_distance(i: int, j: int) -> float:
            key = (min(only_failed[i].id, only_failed[j].id),
                   max(only_failed[i].id, only_failed[j].id))
            return 1.0 - sim_cache.get(key, 0.0)

        # Build a map from point index → cluster index
        point_to_cluster: list[int] = [0] * n
        for cidx, members in enumerate(cluster_members):
            for m in members:
                point_to_cluster[m] = cidx

        sil_scores: list[float] = []
        for i in range(n):
            cidx = point_to_cluster[i]
            cluster = cluster_members[cidx]
            # a(i): mean distance to other points in same cluster
            same = [m for m in cluster if m != i]
            a_i = (sum(_point_distance(i, m) for m in same) / len(same)) if same else 0.0
            # b(i): mean distance to points in nearest other cluster
            b_i = float("inf")
            for other_cidx, other_cluster in enumerate(cluster_members):
                if other_cidx == cidx:
                    continue
                mean_d = sum(_point_distance(i, m) for m in other_cluster) / len(other_cluster)
                if mean_d < b_i:
                    b_i = mean_d
            if b_i == float("inf"):
                b_i = 0.0
            denom = max(a_i, b_i)
            s_i = (b_i - a_i) / denom if denom > 0 else 0.0
            sil_scores.append(s_i)

        avg_silhouette = sum(sil_scores) / len(sil_scores) if sil_scores else 0.0
        if avg_silhouette < _SILHOUETTE_THRESHOLD:
            cluster_members = [[i] for i in range(n)]

    # Build output dicts matching the shape expected by form_hypotheses
    out = []
    for idx, members in enumerate(cluster_members, start=1):
        cluster_failures = [only_failed[m] for m in members]
        fids = [f.id for f in cluster_failures]
        shared_commits = list({
            e.dst for e in graph.edges
            if e.src in fids and e.relation == "caused_by" and e.dst.startswith("commit:")
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
