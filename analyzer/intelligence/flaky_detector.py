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
    lowered = text.lower()
    # NDOD takes priority if any NDOD signal is present
    if any(s in lowered for s in _CATEGORY_SIGNALS.get("NDOD", [])):
        return "NDOD"
    best_cat: str | None = None
    best_hit_count = 0
    best_signal_len = 0
    for cat, signals in _CATEGORY_SIGNALS.items():
        if cat == "NDOD":
            continue
        hits = [s for s in signals if s in lowered]
        count = len(hits)
        max_len = max((len(s) for s in hits), default=0)
        if count > best_hit_count or (count == best_hit_count and max_len > best_signal_len):
            best_cat = cat
            best_hit_count = count
            best_signal_len = max_len
    return best_cat if best_hit_count > 0 else None


def _history_flakiness(failure_id: str, history: dict) -> float:
    """Score 0.0–0.3 based on intermittent appearance in run history.

    Uses intermittency ratio: min(fail_count, pass_count) / total_runs.
    A 50 % fail rate (maximally flaky) gives ratio=0.5 → score=0.3.
    A 10 % or 90 % fail rate gives ratio=0.1 → score=0.06.
    """
    runs = history.get("runs", [])
    total_runs = len(runs)
    if total_runs < 2:
        return 0.0
    fail_count = sum(
        1 for r in runs
        if any(f["id"] == failure_id for f in r.get("failures", []))
    )
    pass_count = total_runs - fail_count
    if fail_count == 0 or pass_count == 0:
        return 0.0
    ratio = min(fail_count, pass_count) / max(total_runs, 1)
    return min(ratio * 0.6, 0.3)


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
