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
