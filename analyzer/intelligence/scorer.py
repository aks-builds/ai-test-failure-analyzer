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
