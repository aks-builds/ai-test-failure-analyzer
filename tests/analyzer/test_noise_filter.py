from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import pytest

from analyzer.workspace_scanner import WorkspaceProfile, NOISE_KEYWORDS
from analyzer.noise_filter import filter_evidence_items, filter_hypotheses


def _profile(mode="FULL_SOURCE", noise_paths=None, keywords=None):
    return WorkspaceProfile(
        mode=mode,
        noise_paths=noise_paths or [],
        noise_keywords=keywords or set(NOISE_KEYWORDS),
    )


@dataclass
class _FakeEvidence:
    source: str
    ref: str = ""
    excerpt: str = ""


@dataclass
class _FakeHypothesis:
    title: str
    buggy_location: str | None
    evidence_chain: list = field(default_factory=list)


# ── Evidence item filtering ───────────────────────────────────────────────────

def test_path_block_drops_item_under_noise_dir(tmp_path):
    noise_dir = tmp_path / "tests" / "fixtures"
    noise_dir.mkdir(parents=True)
    item = {"ref": str(noise_dir / "results.json"), "excerpt": "error"}
    clean, dropped = filter_evidence_items([item], _profile(noise_paths=[noise_dir]))
    assert dropped == 1
    assert clean == []


def test_path_block_does_not_affect_non_noisy_paths():
    item = {"ref": "src/api/routes.py", "excerpt": "endpoint renamed"}
    clean, dropped = filter_evidence_items([item], _profile())
    assert dropped == 0
    assert len(clean) == 1


def test_keyword_block_intentional(tmp_path):
    item = {"ref": "src/app.py", "excerpt": "intentional failure for demo"}
    clean, dropped = filter_evidence_items([item], _profile())
    assert dropped == 1
    assert clean == []


def test_keyword_block_case_insensitive():
    item = {"ref": "src/app.py", "excerpt": "DELIBERATELY broken for testing"}
    clean, dropped = filter_evidence_items([item], _profile())
    assert dropped == 1


def test_keyword_block_on_purpose():
    item = {"ref": "src/app.py", "excerpt": "broken on purpose"}
    clean, dropped = filter_evidence_items([item], _profile())
    assert dropped == 1


def test_keyword_block_expected_to_fail():
    item = {"ref": "src/app.py", "excerpt": "this test is expected to fail"}
    clean, dropped = filter_evidence_items([item], _profile())
    assert dropped == 1


def test_clean_evidence_passes_through():
    item = {"ref": "src/api/routes.py", "excerpt": "endpoint /api/v1 -> /api/v2"}
    clean, dropped = filter_evidence_items([item], _profile())
    assert dropped == 0
    assert clean == [item]


def test_multiple_items_partial_filter():
    items = [
        {"ref": "src/routes.py", "excerpt": "renamed endpoint"},
        {"ref": "src/app.py", "excerpt": "intentional failure"},
    ]
    clean, dropped = filter_evidence_items(items, _profile())
    assert dropped == 1
    assert len(clean) == 1
    assert clean[0]["ref"] == "src/routes.py"


# ── Hypothesis filtering ──────────────────────────────────────────────────────

def test_dedup_removes_identical_fingerprint():
    h1 = _FakeHypothesis("Endpoint renamed", "api/routes.py:44", [_FakeEvidence("git")])
    h2 = _FakeHypothesis("Endpoint renamed", "api/routes.py:44", [_FakeEvidence("git")])
    out, suppressed, _ = filter_hypotheses([h1, h2], _profile())
    assert len(out) == 1
    assert suppressed == 1


def test_dedup_different_buggy_locations_both_kept():
    h1 = _FakeHypothesis("Endpoint renamed", "api/routes.py:44", [_FakeEvidence("git")])
    h2 = _FakeHypothesis("Endpoint renamed", "api/auth.py:12", [_FakeEvidence("git")])
    out, suppressed, _ = filter_hypotheses([h1, h2], _profile())
    assert len(out) == 2
    assert suppressed == 0


def test_tier1_gate_suppresses_test_output_only_hypothesis():
    h = _FakeHypothesis("Fixture failure", "tests/fixtures/result.json",
                        [_FakeEvidence("test_output")])
    out, suppressed, no_fault = filter_hypotheses([h], _profile(mode="FULL_SOURCE"))
    assert len(out) == 0
    assert suppressed == 1
    assert no_fault is True


def test_tier1_gate_passes_git_evidence():
    h = _FakeHypothesis("Route renamed", "api/routes.py:44", [
        _FakeEvidence("test_output"),
        _FakeEvidence("git", "a3f9b2", "rename /api/clips"),
    ])
    out, suppressed, no_fault = filter_hypotheses([h], _profile(mode="FULL_SOURCE"))
    assert len(out) == 1
    assert suppressed == 0
    assert no_fault is False


def test_tier1_gate_passes_logs_evidence():
    h = _FakeHypothesis("DB error", "api/db.py:10", [_FakeEvidence("logs")])
    out, _, no_fault = filter_hypotheses([h], _profile(mode="FULL_SOURCE"))
    assert len(out) == 1
    assert no_fault is False


def test_tier1_gate_passes_config_evidence():
    h = _FakeHypothesis("Config changed", "api/app.py:5", [_FakeEvidence("config")])
    out, _, no_fault = filter_hypotheses([h], _profile(mode="FULL_SOURCE"))
    assert len(out) == 1
    assert no_fault is False


def test_tier1_gate_not_applied_in_api_only_mode():
    h = _FakeHypothesis("404 endpoint", None, [_FakeEvidence("test_output")])
    out, suppressed, no_fault = filter_hypotheses([h], _profile(mode="API_ONLY"))
    assert len(out) == 1
    assert suppressed == 0
    assert no_fault is False


def test_no_fault_only_true_when_input_non_empty():
    out, suppressed, no_fault = filter_hypotheses([], _profile(mode="FULL_SOURCE"))
    assert no_fault is False
