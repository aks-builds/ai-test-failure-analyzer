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
