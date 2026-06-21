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

    # 50% intermittency (5 fail / 5 pass) should score higher than 10% (1 fail / 9 pass)
    fid_50 = make_failure_id("pytest", "suite", "test_50pct", "test.py")
    fid_10 = make_failure_id("pytest", "suite", "test_10pct", "test.py")
    failure_50 = NormalizedFailure(
        id=fid_50, framework="pytest", suite="suite",
        title="test_50pct", file="test.py", status="failed",
    )
    failure_10 = NormalizedFailure(
        id=fid_10, framework="pytest", suite="suite",
        title="test_10pct", file="test.py", status="failed",
    )
    history_50 = {
        "runs": (
            [{"run_id": f"r{i}", "failures": [{"id": fid_50, "status": "failed"}]} for i in range(5)]
            + [{"run_id": f"p{i}", "failures": []} for i in range(5)]
        )
    }
    history_10 = {
        "runs": (
            [{"run_id": "r0", "failures": [{"id": fid_10, "status": "failed"}]}]
            + [{"run_id": f"p{i}", "failures": []} for i in range(9)]
        )
    }
    detect_flaky([failure_50], history=history_50)
    detect_flaky([failure_10], history=history_10)
    assert (failure_50.flakiness_score or 0) > (failure_10.flakiness_score or 0)


def test_flaky_detector_od_vic_and_od_brit_beat_od():
    from analyzer.intelligence.flaky_detector import detect_flaky
    # "setup failed" contains "setup" (OD signal) AND "setup failed" (OD-Vic signal)
    # OD-Vic should win because its matching signal is longer
    failures_vic = [_make_failure("test_setup_fail", "setup failed during initialization")]
    detect_flaky(failures_vic, history=None)
    assert failures_vic[0].flakiness_category == "OD-Vic", (
        f"Expected OD-Vic, got {failures_vic[0].flakiness_category}"
    )

    # "teardown failed" contains "teardown" (OD signal) AND "teardown failed" (OD-Brit signal)
    # OD-Brit should win because its matching signal is longer
    failures_brit = [_make_failure("test_teardown_fail", "teardown failed after test")]
    detect_flaky(failures_brit, history=None)
    assert failures_brit[0].flakiness_category == "OD-Brit", (
        f"Expected OD-Brit, got {failures_brit[0].flakiness_category}"
    )


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


# ── Scorer ────────────────────────────────────────────────────────────────────

def test_scorer_no_evidence_returns_10():
    """Empty graph: raw=0, no caps bite below 55, score clamps to floor of 10."""
    from analyzer.intelligence.scorer import score_cluster
    from analyzer.evidence.graph import EvidenceGraph
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    fid = make_failure_id("pytest", "s", "t", "f.py")
    f = NormalizedFailure(id=fid, framework="pytest", suite="s", title="t", file="f.py",
                          status="failed")
    score, justification = score_cluster("C1", [fid], EvidenceGraph(), [f])
    # raw_weight=0, corroboration=0, flaky=0, contradiction=0 → raw=0
    # tier1_count==0, no source_types → cap at 55 → min(0,55)=0 → max(10,0)=10
    assert score == 10
    assert isinstance(justification, str)


def test_scorer_tier1_evidence_returns_70():
    """Two Tier-1 nodes (commit + log_line) each at weight=2.0 must produce score=70."""
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
    # raw_weight=4.0, int(60)=60, corroboration=min(2*5,20)=10, flaky=0, contradiction=0
    # raw=70, tier1 present → no cap → max(10, min(98, 70))=70
    assert score == 70


def test_scorer_flaky_penalty_reduces_score_to_60():
    """Flat -10 flaky penalty on the two-Tier-1 setup must give score=60."""
    from analyzer.intelligence.scorer import score_cluster
    from analyzer.evidence.graph import EvidenceGraph, EvidenceNode, EvidenceEdge
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    fid = make_failure_id("pytest", "s", "t", "f.py")
    f_flaky = NormalizedFailure(id=fid, framework="pytest", suite="s", title="t",
                                file="f.py", status="failed", flakiness_score=0.7)
    g = EvidenceGraph()
    g.add_node(EvidenceNode(id=fid, type="failure", ref="f.py", weight=0.0, excerpt=""))
    g.add_node(EvidenceNode(id="commit:abc", type="commit", ref="abc", weight=2.0, excerpt="rename"))
    g.add_node(EvidenceNode(id="log:0", type="log_line", ref="app.log:42", weight=2.0, excerpt="ERROR"))
    g.add_edge(EvidenceEdge(src=fid, dst="commit:abc", relation="caused_by", weight=2.0))
    g.add_edge(EvidenceEdge(src=fid, dst="log:0", relation="related_to", weight=2.0))
    score, _ = score_cluster("C1", [fid], g, [f_flaky])
    # Same as tier1 test but flakiness_score=0.7 → flaky_penalty=10
    # raw=60+10-10-0=60, tier1 present → no cap → max(10, min(98, 60))=60
    assert score == 60


def test_scorer_no_tier1_capped_at_40():
    """Four Tier-2 nodes across 3 source types: raw=75 gets capped to 40 by no-tier1 rule."""
    from analyzer.intelligence.scorer import score_cluster
    from analyzer.evidence.graph import EvidenceGraph, EvidenceNode, EvidenceEdge
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    fid = make_failure_id("pytest", "s", "t", "f.py")
    f = NormalizedFailure(id=fid, framework="pytest", suite="s", title="t", file="f.py",
                          status="failed")
    g = EvidenceGraph()
    g.add_node(EvidenceNode(id=fid, type="failure", ref="f.py", weight=0.0, excerpt=""))
    # 4 Tier-2 nodes (weight=1.0) across 3 distinct source types
    g.add_node(EvidenceNode(id="log:0", type="log_line", ref="app.log:1", weight=1.0, excerpt=""))
    g.add_node(EvidenceNode(id="log:1", type="log_line", ref="app.log:2", weight=1.0, excerpt=""))
    g.add_node(EvidenceNode(id="dep:0", type="dep_change", ref="pkg.json", weight=1.0, excerpt=""))
    g.add_node(EvidenceNode(id="cfg:0", type="config", ref="app.cfg", weight=1.0, excerpt=""))
    g.add_edge(EvidenceEdge(src=fid, dst="log:0", relation="related_to", weight=1.0))
    g.add_edge(EvidenceEdge(src=fid, dst="log:1", relation="related_to", weight=1.0))
    g.add_edge(EvidenceEdge(src=fid, dst="dep:0", relation="related_to", weight=1.0))
    g.add_edge(EvidenceEdge(src=fid, dst="cfg:0", relation="related_to", weight=1.0))
    score, _ = score_cluster("C1", [fid], g, [f])
    # raw_weight=4.0, int(60)=60, corroboration=min(3*5,20)=15, flaky=0, contradiction=0
    # raw=75, tier1_count==0 and source_types present → cap at 40 → min(75,40)=40
    # max(10, min(98, 40))=40
    assert score == 40


def test_scorer_contradiction_penalty():
    """Orphan Tier-1 node (in graph but not linked to cluster) fires -15 penalty."""
    from analyzer.intelligence.scorer import score_cluster
    from analyzer.evidence.graph import EvidenceGraph, EvidenceNode
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    fid = make_failure_id("pytest", "s", "t", "f.py")
    f = NormalizedFailure(id=fid, framework="pytest", suite="s", title="t", file="f.py",
                          status="failed")
    g = EvidenceGraph()
    # Tier-1 node exists in graph but has NO edge from the cluster failure
    g.add_node(EvidenceNode(id="commit:abc", type="commit", ref="abc", weight=2.0, excerpt=""))
    score, justification = score_cluster("C1", [fid], g, [f])
    # raw_weight=0, corroboration=0, flaky=0
    # tier1_nodes_in_graph=[commit:abc], tier1_linked_to_cluster=[] → contradiction_penalty=15
    # raw=0+0-0-15=-15, tier1_count==0 and no source_types → cap at 55 → min(-15,55)=-15
    # max(10, min(98, -15))=10
    assert score == 10
    assert "contradiction" in justification


def test_clusterer_silhouette_fallback():
    """4 heterogeneous failures should fall back to 4 singleton clusters (silhouette < 0.6)."""
    from analyzer.intelligence.clusterer import cluster_failures_v2
    from analyzer.parsers.base import NormalizedFailure, make_failure_id
    from analyzer.evidence.graph import EvidenceGraph

    def _f(title, error):
        fid = make_failure_id("pytest", "suite", title, f"{title}.py")
        return NormalizedFailure(
            id=fid, framework="pytest", suite="suite",
            title=title, file=f"{title}.py", status="failed",
            error_message=error,
        )

    # Four completely different error types — no shared words, no shared commits
    fa = _f("test_auth",    "401 unauthorized jwt token expired invalid signature")
    fb = _f("test_db",      "database connection refused postgresql port 5432 timeout")
    fc = _f("test_render",  "segmentation fault core dumped memory address 0x0000")
    fd = _f("test_network", "dns lookup failed nxdomain hostname resolution error")

    clusters = cluster_failures_v2([fa, fb, fc, fd], EvidenceGraph())
    # Silhouette should be < 0.6 for these heterogeneous failures → fallback to 4 singletons
    assert len(clusters) == 4, (
        f"Expected 4 singleton clusters (silhouette fallback), got {len(clusters)}"
    )
