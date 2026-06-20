"""Robot Framework XML results parser."""
from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class RobotXmlParser(Parser):
    """Parses Robot Framework output.xml.
    Sniff: <robot generator="Robot ..."> root element."""
    framework = "robot"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "<robot" in text and 'generator="Robot' in text

    @classmethod
    def _parse_suite(cls, suite_el, results, suite_name=""):
        name = suite_el.get("name", suite_name)
        for test in suite_el.findall("test"):
            test_name = test.get("name", "")
            status_el = test.find("status")
            if status_el is None:
                continue
            raw_status = status_el.get("status", "UNKNOWN")
            status = "failed" if raw_status == "FAIL" else (
                "skipped" if raw_status == "SKIP" else "passed"
            )
            error_msg = (status_el.text or "").strip() or None
            # Collect FAIL messages from keywords
            if not error_msg:
                for msg in test.iter("msg"):
                    if msg.get("level") == "FAIL":
                        error_msg = msg.text
                        break
            expected, actual = parse_assertion(error_msg, None)
            http = parse_http(test_name, error_msg, None)
            source = suite_el.get("source", "unknown")
            results.append(NormalizedFailure(
                id=make_failure_id("robot", name, test_name, source),
                framework="robot",
                suite=name,
                title=test_name,
                file=source,
                status=status,
                error_message=error_msg,
                expected=expected,
                actual=actual,
                http=http,
                raw={"suite": name},
            ))
        for child_suite in suite_el.findall("suite"):
            cls._parse_suite(child_suite, results, name)

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        root = ET.parse(str(path)).getroot()
        results: list[NormalizedFailure] = []
        for suite in root.findall("suite"):
            cls._parse_suite(suite, results)
        return results
