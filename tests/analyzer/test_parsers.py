"""Parser tests — all four frameworks parse to the same NormalizedFailure shape."""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzer.parsers import detect, parse
from analyzer.parsers.base import NormalizedFailure

FIXTURES = Path(__file__).parent / "fixtures"
DEMO_RESULTS = FIXTURES / "playwright_results.json"


# ── Detection ────────────────────────────────────────────────────────────────


def test_detect_playwright():
    from analyzer.parsers.playwright_json import PlaywrightJsonParser
    assert detect(DEMO_RESULTS) is PlaywrightJsonParser


def test_detect_pytest_junit():
    from analyzer.parsers.pytest_junit import PytestJUnitParser
    assert detect(FIXTURES / "pytest_junit.xml") is PytestJUnitParser


def test_detect_jest():
    from analyzer.parsers.jest_json import JestJsonParser
    assert detect(FIXTURES / "jest_results.json") is JestJsonParser


def test_detect_cypress():
    from analyzer.parsers.cypress_json import CypressJsonParser
    assert detect(FIXTURES / "cypress_results.json") is CypressJsonParser


def test_detect_unknown_format(tmp_path):
    p = tmp_path / "random.txt"
    p.write_text("not a test report")
    assert detect(p) is None


# ── Parsing ──────────────────────────────────────────────────────────────────


def _assert_shape(failures: list[NormalizedFailure], framework: str, min_failed: int = 1):
    assert isinstance(failures, list)
    assert failures, "expected at least one failure record"
    failed = [f for f in failures if f.status == "failed"]
    assert len(failed) >= min_failed
    for f in failures:
        assert f.framework == framework
        assert f.title
        # IDs are stable and uniform length
        assert len(f.id) == 16


def test_parse_playwright():
    fw, failures = parse(DEMO_RESULTS)
    assert fw == "playwright"
    _assert_shape(failures, "playwright", min_failed=3)
    # The demo data has 3 failed + 3 passed
    assert sum(1 for f in failures if f.status == "failed") == 3
    assert sum(1 for f in failures if f.status == "passed") == 3


def test_parse_pytest_junit():
    fw, failures = parse(FIXTURES / "pytest_junit.xml")
    assert fw == "pytest"
    _assert_shape(failures, "pytest", min_failed=2)


def test_parse_jest():
    fw, failures = parse(FIXTURES / "jest_results.json")
    assert fw == "jest"
    _assert_shape(failures, "jest", min_failed=2)


def test_parse_cypress():
    fw, failures = parse(FIXTURES / "cypress_results.json")
    assert fw == "cypress"
    _assert_shape(failures, "cypress", min_failed=2)


# ── Assertion extraction ─────────────────────────────────────────────────────


def test_playwright_http_extraction():
    _, failures = parse(DEMO_RESULTS)
    failed = [f for f in failures if f.status == "failed"]
    # All three demo failures should have parsed HTTP statuses
    assert any(f.actual == "404" or (f.http and f.http.get("status_got") == 404) for f in failed)
    assert any(f.expected in ("200", "201") or (f.http and f.http.get("status_expected") in (200, 201)) for f in failed)


def test_explicit_framework_override():
    """Passing framework= bypasses detection."""
    fw, failures = parse(FIXTURES / "jest_results.json", framework="jest")
    assert fw == "jest"
    assert len(failures) >= 2


def test_unknown_framework_raises():
    with pytest.raises(ValueError):
        parse(DEMO_RESULTS, framework="bogus-framework")
