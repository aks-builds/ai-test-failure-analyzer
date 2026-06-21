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


def test_detect_newman():
    from analyzer.parsers.newman_json import NewmanJsonParser
    assert detect(FIXTURES / "newman_results.json") is NewmanJsonParser


def test_parse_newman():
    fw, failures = parse(FIXTURES / "newman_results.json")
    assert fw == "newman"
    assert isinstance(failures, list)
    failed = [f for f in failures if f.status == "failed"]
    assert len(failed) == 1
    assert failed[0].title == "Create clip — Status code is 201"
    assert failed[0].http is not None
    assert failed[0].http["method"] == "POST"
    assert failed[0].http["status_got"] == 404
    assert failed[0].http["response_time_ms"] == 142
    assert failed[0].file == ""
    assert failed[0].line is None


def test_parse_newman_passed_items_included():
    _, failures = parse(FIXTURES / "newman_results.json")
    passed = [f for f in failures if f.status == "passed"]
    assert len(passed) == 1
    assert passed[0].title == "List clips"


def test_detect_k6():
    from analyzer.parsers.k6_json import K6JsonParser
    with open(FIXTURES / "k6_results.json", "rb") as f:
        sample = f.read(4096)
    assert K6JsonParser.can_parse(sample)


def test_parse_k6():
    from analyzer.parsers.k6_json import K6JsonParser
    failures = K6JsonParser.parse(FIXTURES / "k6_results.json")
    assert K6JsonParser.framework == "k6"
    failed = [f for f in failures if f.status == "failed"]
    assert len(failed) == 1
    assert failed[0].title == "status is 200"
    assert failed[0].suite == "k6 load test"
    assert "5/50" in (failed[0].error_message or "")
    assert failed[0].http is not None
    assert failed[0].http["response_time_ms"] == 720  # int(720.5)
    assert failed[0].file == ""
    assert failed[0].line is None


def test_parse_k6_passed_checks_excluded():
    from analyzer.parsers.k6_json import K6JsonParser
    failures = K6JsonParser.parse(FIXTURES / "k6_results.json")
    # "response time < 500ms" has 0 fails — should not appear as a failed result
    assert not any(f.title == "response time < 500ms" and f.status == "failed" for f in failures)


def test_normalized_failure_new_fields_default_none():
    """New v2 fields must default to None / empty dict for backward compat."""
    from analyzer.parsers.base import NormalizedFailure
    f = NormalizedFailure(
        id="abc", framework="pytest", suite="s", title="t", file="f.py"
    )
    assert f.flakiness_score is None
    assert f.flakiness_category is None
    assert f.ctrf_extra == {}


def test_normalized_failure_new_fields_set():
    from analyzer.parsers.base import NormalizedFailure
    f = NormalizedFailure(
        id="abc", framework="pytest", suite="s", title="t", file="f.py",
        flakiness_score=0.75,
        flakiness_category="ID",
        ctrf_extra={"foo": "bar"},
    )
    assert f.flakiness_score == 0.75
    assert f.flakiness_category == "ID"
    assert f.ctrf_extra == {"foo": "bar"}


# ── ParserRegistry ────────────────────────────────────────────────────────────


def test_parser_registry_detect_playwright(tmp_path):
    """Registry detect() must return PlaywrightJsonParser for a playwright file."""
    import json
    from analyzer.parsers.registry import ParserRegistry
    from analyzer.parsers.playwright_json import PlaywrightJsonParser

    # Playwright JSON shape requires "config", "suites", and "specs" keys.
    report = {
        "config": {},
        "suites": [{"title": "suite", "specs": []}],
        "stats": {},
    }
    p = tmp_path / "results.json"
    p.write_text(json.dumps(report))
    result = ParserRegistry.detect(p)
    assert result is PlaywrightJsonParser


def test_parser_registry_unknown_returns_none(tmp_path):
    from analyzer.parsers.registry import ParserRegistry
    p = tmp_path / "unknown.json"
    p.write_text('{"foo": "bar"}')
    result = ParserRegistry.detect(p)
    assert result is None


# ── fixtures helper ───────────────────────────────────────────────────────────


@pytest.fixture
def fixtures():
    return Path(__file__).parent / "fixtures"


# ── Vitest ──────────────────────────────────────────────────────────────────

def test_vitest_can_parse(fixtures):
    from analyzer.parsers.vitest_json import VitestJsonParser
    assert VitestJsonParser.can_parse((fixtures / "vitest_results.json").read_bytes())


def test_vitest_cannot_parse_playwright(fixtures):
    from analyzer.parsers.vitest_json import VitestJsonParser
    assert not VitestJsonParser.can_parse((fixtures / "playwright_results.json").read_bytes())


def test_vitest_parse_returns_failures(fixtures):
    from analyzer.parsers.vitest_json import VitestJsonParser
    results = VitestJsonParser.parse(fixtures / "vitest_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "formats ISO string correctly" in failed[0].title
    assert failed[0].framework == "vitest"


# ── WDIO ─────────────────────────────────────────────────────────────────────

def test_wdio_can_parse(fixtures):
    from analyzer.parsers.wdio_json import WdioJsonParser
    assert WdioJsonParser.can_parse((fixtures / "wdio_results.json").read_bytes())


def test_wdio_parse_returns_failures(fixtures):
    from analyzer.parsers.wdio_json import WdioJsonParser
    results = WdioJsonParser.parse(fixtures / "wdio_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "wdio"


# ── Detox ────────────────────────────────────────────────────────────────────

def test_detox_can_parse(fixtures):
    from analyzer.parsers.detox_json import DetoxJsonParser
    assert DetoxJsonParser.can_parse((fixtures / "detox_results.json").read_bytes())


def test_detox_parse_returns_failures(fixtures):
    from analyzer.parsers.detox_json import DetoxJsonParser
    results = DetoxJsonParser.parse(fixtures / "detox_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "detox"


# ── Mocha ────────────────────────────────────────────────────────────────────

def test_mocha_can_parse(fixtures):
    from analyzer.parsers.mocha_json import MochaJsonParser
    assert MochaJsonParser.can_parse((fixtures / "mocha_results.json").read_bytes())


def test_mocha_parse_returns_failures(fixtures):
    from analyzer.parsers.mocha_json import MochaJsonParser
    results = MochaJsonParser.parse(fixtures / "mocha_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "POST /users" in failed[0].title
    assert failed[0].framework == "mocha"


# ── Go test JSON ──────────────────────────────────────────────────────────────

def test_go_test_can_parse(fixtures):
    from analyzer.parsers.go_test_json import GoTestJsonParser
    assert GoTestJsonParser.can_parse((fixtures / "go_test_results.ndjson").read_bytes())


def test_go_test_cannot_parse_json_object(fixtures):
    from analyzer.parsers.go_test_json import GoTestJsonParser
    assert not GoTestJsonParser.can_parse(b'{"testResults": []}')


def test_go_test_parse_returns_failures(fixtures):
    from analyzer.parsers.go_test_json import GoTestJsonParser
    results = GoTestJsonParser.parse(fixtures / "go_test_results.ndjson")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "TestCreateUser" in failed[0].title
    assert failed[0].framework == "go"
    assert "404" in (failed[0].error_message or "")


# ── RSpec ─────────────────────────────────────────────────────────────────────

def test_rspec_can_parse(fixtures):
    from analyzer.parsers.rspec_json import RSpecJsonParser
    assert RSpecJsonParser.can_parse((fixtures / "rspec_results.json").read_bytes())


def test_rspec_parse_returns_failures(fixtures):
    from analyzer.parsers.rspec_json import RSpecJsonParser
    results = RSpecJsonParser.parse(fixtures / "rspec_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "rspec"
    assert failed[0].line == 12


# ── PHPUnit ───────────────────────────────────────────────────────────────────

def test_phpunit_can_parse(fixtures):
    from analyzer.parsers.phpunit_xml import PHPUnitXmlParser
    assert PHPUnitXmlParser.can_parse((fixtures / "phpunit_results.xml").read_bytes())


def test_phpunit_parse_returns_failures(fixtures):
    from analyzer.parsers.phpunit_xml import PHPUnitXmlParser
    results = PHPUnitXmlParser.parse(fixtures / "phpunit_results.xml")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "phpunit"


# ── NUnit ─────────────────────────────────────────────────────────────────────

def test_nunit_can_parse(fixtures):
    from analyzer.parsers.nunit_xml import NUnitXmlParser
    assert NUnitXmlParser.can_parse((fixtures / "nunit_results.xml").read_bytes())


def test_nunit_parse_returns_failures(fixtures):
    from analyzer.parsers.nunit_xml import NUnitXmlParser
    results = NUnitXmlParser.parse(fixtures / "nunit_results.xml")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "nunit"


# ── xUnit ─────────────────────────────────────────────────────────────────────

def test_xunit_can_parse(fixtures):
    from analyzer.parsers.xunit_xml import XUnitXmlParser
    assert XUnitXmlParser.can_parse((fixtures / "xunit_results.xml").read_bytes())


def test_xunit_parse_returns_failures(fixtures):
    from analyzer.parsers.xunit_xml import XUnitXmlParser
    results = XUnitXmlParser.parse(fixtures / "xunit_results.xml")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "xunit"


# ── Robot Framework ───────────────────────────────────────────────────────────

def test_robot_can_parse(fixtures):
    from analyzer.parsers.robot_xml import RobotXmlParser
    assert RobotXmlParser.can_parse((fixtures / "robot_results.xml").read_bytes())


def test_robot_parse_returns_failures(fixtures):
    from analyzer.parsers.robot_xml import RobotXmlParser
    results = RobotXmlParser.parse(fixtures / "robot_results.xml")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "Create User" in failed[0].title
    assert failed[0].framework == "robot"


# ── Artillery ─────────────────────────────────────────────────────────────────

def test_artillery_can_parse(fixtures):
    from analyzer.parsers.artillery_json import ArtilleryJsonParser
    assert ArtilleryJsonParser.can_parse((fixtures / "artillery_results.json").read_bytes())


def test_artillery_parse_returns_failures(fixtures):
    from analyzer.parsers.artillery_json import ArtilleryJsonParser
    results = ArtilleryJsonParser.parse(fixtures / "artillery_results.json")
    # Artillery reports aggregate errors as failures
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) >= 1
    assert failed[0].framework == "artillery"


# ── Gatling ───────────────────────────────────────────────────────────────────

def test_gatling_can_parse(fixtures):
    from analyzer.parsers.gatling_log import GatlingLogParser
    assert GatlingLogParser.can_parse((fixtures / "gatling_simulation.log").read_bytes())


def test_gatling_cannot_parse_json(fixtures):
    from analyzer.parsers.gatling_log import GatlingLogParser
    assert not GatlingLogParser.can_parse(b'{"testResults": []}')


def test_gatling_parse_returns_failures(fixtures):
    from analyzer.parsers.gatling_log import GatlingLogParser
    results = GatlingLogParser.parse(fixtures / "gatling_simulation.log")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "/api/users/register" in failed[0].title
    assert failed[0].framework == "gatling"


# ── Pact ──────────────────────────────────────────────────────────────────────

def test_pact_can_parse(fixtures):
    from analyzer.parsers.pact_json import PactJsonParser
    assert PactJsonParser.can_parse((fixtures / "pact_results.json").read_bytes())


def test_pact_parse_returns_failures(fixtures):
    from analyzer.parsers.pact_json import PactJsonParser
    results = PactJsonParser.parse(fixtures / "pact_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "create a user" in failed[0].title
    assert failed[0].framework == "pact"


# ── SARIF ─────────────────────────────────────────────────────────────────────

def test_sarif_can_parse(fixtures):
    from analyzer.parsers.sarif_json import SARIFJsonParser
    assert SARIFJsonParser.can_parse((fixtures / "sarif_results.json").read_bytes())


def test_sarif_parse_returns_failures(fixtures):
    from analyzer.parsers.sarif_json import SARIFJsonParser
    results = SARIFJsonParser.parse(fixtures / "sarif_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "sarif"
    assert "sql" in failed[0].title.lower() or "sql" in (failed[0].error_message or "").lower()


# ── CTRF ──────────────────────────────────────────────────────────────────────

def test_ctrf_can_parse(fixtures):
    from analyzer.parsers.ctrf_json import CTRFJsonParser
    assert CTRFJsonParser.can_parse((fixtures / "ctrf_results.json").read_bytes())


def test_ctrf_parse_returns_failures(fixtures):
    from analyzer.parsers.ctrf_json import CTRFJsonParser
    results = CTRFJsonParser.parse(fixtures / "ctrf_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "POST /api/users" in failed[0].title
    assert failed[0].framework == "ctrf"


# ── Allure ────────────────────────────────────────────────────────────────────

def test_allure_can_parse(fixtures):
    from analyzer.parsers.allure_json import AllureJsonParser
    assert AllureJsonParser.can_parse((fixtures / "allure_results.json").read_bytes())


def test_allure_parse_returns_failures(fixtures):
    from analyzer.parsers.allure_json import AllureJsonParser
    results = AllureJsonParser.parse(fixtures / "allure_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "allure"


# ── MSTest / TRX ──────────────────────────────────────────────────────────────

def test_mstest_can_parse(fixtures):
    from analyzer.parsers.mstest_xml import MSTestXmlParser
    assert MSTestXmlParser.can_parse((fixtures / "mstest_results.xml").read_bytes())


def test_mstest_parse_returns_failures(fixtures):
    from analyzer.parsers.mstest_xml import MSTestXmlParser
    results = MSTestXmlParser.parse(fixtures / "mstest_results.xml")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "mstest"
