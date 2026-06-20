"""xUnit.net XML results parser."""
from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class XUnitXmlParser(Parser):
    """Parses xUnit.net XML output.
    Sniff: <assemblies> root element."""
    framework = "xunit"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "<assemblies" in text and "<collection" in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        root = ET.parse(str(path)).getroot()
        results: list[NormalizedFailure] = []
        for test in root.iter("test"):
            raw_result = test.get("result", "Unknown")
            status = "failed" if raw_result in ("Fail", "Error") else (
                "skipped" if raw_result == "Skip" else "passed"
            )
            name = test.get("name", "")
            type_ = test.get("type", "")
            method = test.get("method", "")
            title = method or name
            failure_el = test.find("failure")
            error_msg = error_stack = None
            if failure_el is not None:
                msg_el = failure_el.find("message")
                st_el = failure_el.find("stack-trace")
                error_msg = msg_el.text if msg_el is not None else None
                error_stack = st_el.text if st_el is not None else None
            expected, actual = parse_assertion(error_msg, error_stack)
            http = parse_http(title, error_msg, error_stack)
            duration_ms = int(float(test.get("time", 0)) * 1000)
            results.append(NormalizedFailure(
                id=make_failure_id("xunit", type_, title, type_),
                framework="xunit",
                suite=type_,
                title=title,
                file=type_,
                duration_ms=duration_ms,
                status=status,
                error_message=error_msg,
                error_stack=error_stack,
                expected=expected,
                actual=actual,
                http=http,
                raw={"name": name},
            ))
        return results
