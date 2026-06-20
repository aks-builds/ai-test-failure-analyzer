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
