"""PHPUnit XML results parser."""
from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class PHPUnitXmlParser(Parser):
    """Parses PHPUnit XML output (--log-junit or default).
    Sniff: <phpunit> root element."""
    framework = "phpunit"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "<phpunit" in text and "<testsuite" in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        root = ET.parse(str(path)).getroot()
        results: list[NormalizedFailure] = []
        for tc in root.iter("testcase"):
            suite = tc.get("class") or tc.get("classname") or ""
            title = tc.get("name", "")
            file_path = tc.get("file", "unknown")
            line = int(tc.get("line", 0)) or None
            duration_ms = int(float(tc.get("time", 0)) * 1000)
            failure = tc.find("failure")
            if failure is None:
                failure = tc.find("error")
            if failure is not None:
                error_msg = failure.text or failure.get("type") or ""
                expected, actual = parse_assertion(error_msg, None)
                http = parse_http(title, error_msg, None)
                status = "failed"
            else:
                error_msg = expected = actual = http = None
                status = "skipped" if tc.find("skipped") is not None else "passed"
            results.append(NormalizedFailure(
                id=make_failure_id("phpunit", suite, title, file_path),
                framework="phpunit",
                suite=suite,
                title=title,
                file=file_path,
                line=line,
                duration_ms=duration_ms,
                status=status,
                error_message=error_msg,
                expected=expected,
                actual=actual,
                http=http,
                raw={"class": suite, "name": title},
            ))
        return results
