"""NUnit 3 XML results parser."""
from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class NUnitXmlParser(Parser):
    """Parses NUnit 3 XML output.
    Sniff: <test-run> root element with engine-version attribute."""
    framework = "nunit"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "<test-run" in text and "engine-version" in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        root = ET.parse(str(path)).getroot()
        results: list[NormalizedFailure] = []
        for tc in root.iter("test-case"):
            raw_result = tc.get("result", "Unknown")
            status = "failed" if raw_result == "Failed" else (
                "skipped" if raw_result in ("Skipped", "Ignored") else "passed"
            )
            fullname = tc.get("fullname") or tc.get("name", "")
            classname = tc.get("classname") or fullname.rsplit(".", 1)[0]
            title = tc.get("name") or tc.get("methodname", "")
            failure_el = tc.find("failure")
            error_msg = error_stack = None
            if failure_el is not None:
                msg_el = failure_el.find("message")
                st_el = failure_el.find("stack-trace")
                error_msg = msg_el.text if msg_el is not None else None
                error_stack = st_el.text if st_el is not None else None
            expected, actual = parse_assertion(error_msg, error_stack)
            http = parse_http(title, error_msg, error_stack)
            duration_ms = int(float(tc.get("duration", 0)) * 1000)
            results.append(NormalizedFailure(
                id=make_failure_id("nunit", classname, title, classname),
                framework="nunit",
                suite=classname,
                title=title,
                file=classname,
                duration_ms=duration_ms,
                status=status,
                error_message=error_msg,
                error_stack=error_stack,
                expected=expected,
                actual=actual,
                http=http,
                raw={"fullname": fullname},
            ))
        return results
