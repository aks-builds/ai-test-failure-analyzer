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
