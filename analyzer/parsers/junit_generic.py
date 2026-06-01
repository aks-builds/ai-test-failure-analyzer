"""Generic JUnit XML reader. Used by pytest, Jest's JUnit reporter,
Cypress's JUnit reporter, WebdriverIO, etc. — anything that emits
JUnit-compatible XML.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from ..security import cap_raw_record
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


def _testcase_to_failure(tc: etree._Element, suite_name: str, framework: str) -> NormalizedFailure:
    title = tc.attrib.get("name", "")
    file = tc.attrib.get("file") or tc.attrib.get("classname", "")
    line_s = tc.attrib.get("line")
    line = int(line_s) if line_s and line_s.isdigit() else None
    duration_s = tc.attrib.get("time")
    duration_ms = int(float(duration_s) * 1000) if duration_s else None

    failure_el = tc.find("failure")
    if failure_el is None:
        failure_el = tc.find("error")
    skipped_el = tc.find("skipped")

    if skipped_el is not None:
        status = "skipped"
        err_msg = skipped_el.attrib.get("message")
        err_stack = (skipped_el.text or "").strip() or None
    elif failure_el is not None:
        status = "failed"
        err_msg = failure_el.attrib.get("message")
        err_stack = (failure_el.text or "").strip() or None
    else:
        status = "passed"
        err_msg = None
        err_stack = None

    expected, actual = parse_assertion(err_msg, err_stack)
    http = parse_http(title, err_msg, err_stack)

    return NormalizedFailure(
        id=make_failure_id(framework, suite_name, title, file),
        framework=framework,
        suite=suite_name,
        title=title,
        file=file,
        line=line,
        duration_ms=duration_ms,
        status=status,  # type: ignore[arg-type]
        error_message=err_msg,
        error_stack=err_stack,
        expected=expected,
        actual=actual,
        http=http,
        attachments=[],
        raw=cap_raw_record({"attrib": dict(tc.attrib)}),
    )


def read_junit(path: Path, framework: str) -> list[NormalizedFailure]:
    """Parse a JUnit XML file. Tolerant of both ``<testsuites>`` and bare ``<testsuite>`` roots."""
    tree = etree.parse(str(path))
    root = tree.getroot()
    suites = root.findall(".//testsuite") if root.tag == "testsuites" else [root]

    out: list[NormalizedFailure] = []
    for suite in suites:
        suite_name = suite.attrib.get("name", "")
        for tc in suite.findall("testcase"):
            out.append(_testcase_to_failure(tc, suite_name, framework))
    return out


class JUnitXmlParser(Parser):
    """Fallback parser for any JUnit XML we couldn't otherwise classify."""

    framework = "junit"

    @classmethod
    def can_parse(cls, sample: str | bytes) -> bool:
        if isinstance(sample, bytes):
            try:
                sample = sample.decode("utf-8", errors="replace")
            except Exception:
                return False
        s = sample.lstrip()
        return s.startswith("<?xml") and ("<testsuite" in s or "<testsuites" in s)

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        return read_junit(path, framework=cls.framework)
