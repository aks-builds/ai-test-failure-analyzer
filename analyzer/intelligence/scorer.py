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

    # Flaky penalty: flat -10 if ANY failure in cluster has flakiness_score >= 0.5
    cluster_failures = [f for f in failures if f.id in fid_set]
    flaky_penalty = 10 if any(
        f.flakiness_score is not None and f.flakiness_score >= 0.5
        for f in cluster_failures
    ) else 0

    # Contradiction penalty: -15 if cluster IS linked to evidence but all of it is Tier-2
    # (evidence present but no Tier-1 node linked = weak signal only)
    any_linked = bool(linked_nodes)
    tier1_linked = any(n.weight >= 2.0 for n in linked_nodes)
    contradiction_penalty = 15 if (any_linked and not tier1_linked) else 0

    raw = int(raw_weight * 15) + corroboration - flaky_penalty - contradiction_penalty

    # Hard caps
    if tier1_count == 0 and not source_types:
        # Single test output only — no evidence at all
        raw = min(raw, 40)
    if tier1_count == 0 and source_types:
        # Some Tier-2 evidence present but no Tier-1
        raw = min(raw, 55)

    score = max(10, min(98, raw))

    # Build justification string
    parts = []
    if source_types:
        parts.append(f"evidence: {'+'.join(sorted(source_types))}")
    if tier1_count:
        parts.append(f"{tier1_count} Tier-1 source(s)")
    if flaky_penalty:
        parts.append("probable flake(s) penalised")
    if contradiction_penalty:
        parts.append("contradiction penalised (orphan Tier-1 node)")
    justification = " · ".join(parts) if parts else "test output only"

    return score, justification
