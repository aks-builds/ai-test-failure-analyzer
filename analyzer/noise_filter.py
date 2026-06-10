# analyzer/noise_filter.py
from __future__ import annotations

import hashlib
from pathlib import Path

from .workspace_scanner import WorkspaceProfile

_TIER1_SOURCES = {"git", "logs", "config"}


def _path_is_noisy(ref: str | None, noise_paths: list[Path]) -> bool:
    if not ref or not noise_paths:
        return False
    try:
        p = Path(ref)
    except Exception:
        return False
    for noise_dir in noise_paths:
        try:
            p.resolve().relative_to(noise_dir.resolve())
            return True
        except ValueError:
            pass
        # Also match by string prefix (for relative paths stored in evidence)
        if str(p).startswith(str(noise_dir)):
            return True
    return False


def _text_is_noisy(text: str | None, keywords: set[str]) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def _fingerprint(title: str, buggy_location: str | None) -> str:
    seed = f"{title}::{buggy_location or ''}"
    return hashlib.sha1(seed.encode()).hexdigest()[:12]


def filter_evidence_items(
    items: list[dict],
    profile: WorkspaceProfile,
) -> tuple[list[dict], int]:
    """Remove noisy evidence items (path-blocked or keyword-blocked).

    Returns (clean_items, dropped_count).
    """
    clean: list[dict] = []
    dropped = 0
    for item in items:
        ref = item.get("ref") or item.get("path") or ""
        text = item.get("excerpt") or item.get("text") or ""
        if _path_is_noisy(ref, profile.noise_paths):
            dropped += 1
            continue
        if _text_is_noisy(text, profile.noise_keywords):
            dropped += 1
            continue
        clean.append(item)
    return clean, dropped


def filter_hypotheses(
    hypotheses: list,
    profile: WorkspaceProfile,
) -> tuple[list, int, bool]:
    """Deduplicate and Tier-1 gate hypotheses.

    Rules applied in order:
      3. Dedup — hypothesis fingerprint already seen → DROP
      4. Tier-1 gate (FULL_SOURCE only) — no Tier-1 evidence → SUPPRESS

    Returns (kept, suppressed_count, no_app_fault).
    no_app_fault is True only when FULL_SOURCE, input was non-empty, and
    everything was suppressed by Tier-1 gating.
    """
    seen: set[str] = set()
    kept: list = []
    suppressed = 0

    for h in hypotheses:
        fp = _fingerprint(h.title, h.buggy_location)
        if fp in seen:
            suppressed += 1
            continue
        seen.add(fp)

        if profile.mode == "FULL_SOURCE":
            has_tier1 = any(
                getattr(e, "source", None) in _TIER1_SOURCES
                for e in h.evidence_chain
            )
            if not has_tier1:
                suppressed += 1
                continue

        kept.append(h)

    no_app_fault = (
        profile.mode == "FULL_SOURCE"
        and len(hypotheses) > 0
        and len(kept) == 0
    )
    return kept, suppressed, no_app_fault
