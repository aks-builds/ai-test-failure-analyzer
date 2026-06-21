"""MSTest TRX (Visual Studio Test Results) parser."""
from __future__ import annotations
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http

_NS = {"ms": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}


class MSTestXmlParser(Parser):
    """Parses MSTest TRX XML output.
    Sniff: <TestRun xmlns=...vstestresults...> root element."""
    framework = "mstest"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "vstestresults" in text or ("TestRun" in text and "UnitTestResult" in text)

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        root = ET.parse(str(path)).getroot()
        # Handle both namespaced and non-namespaced TRX files
        namespaced = root.tag.startswith("{")
        results: list[NormalizedFailure] = []

        def find_all(parent, tag):
            if namespaced:
                return parent.findall(f"ms:{tag}", _NS) or parent.findall(f".//ms:{tag}", _NS)
            return parent.findall(f".//{tag}")

        def find_one(parent, tag):
            if namespaced:
                el = parent.find(f"ms:{tag}", _NS)
                if el is None:
                    el = parent.find(f".//ms:{tag}", _NS)
                return el
            return parent.find(f".//{tag}")

        for result in find_all(root, "UnitTestResult"):
            outcome = result.get("outcome", "Unknown")
            status = "failed" if outcome == "Failed" else (
                "skipped" if outcome in ("NotExecuted", "Ignored") else "passed"
            )
            test_name = result.get("testName", "")
            duration_str = result.get("duration", "00:00:00.000")
            # Parse duration "HH:MM:SS.mmm"
            parts = re.split(r"[:.]", duration_str)
            duration_ms = 0
            try:
                if len(parts) >= 4:
                    duration_ms = (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000 + int(parts[3][:3])
            except ValueError:
                pass
            error_msg = error_stack = None
            output_el = find_one(result, "Output")
            if output_el is not None:
                err_el = find_one(output_el, "ErrorInfo")
                if err_el is not None:
                    msg_el = find_one(err_el, "Message")
                    st_el = find_one(err_el, "StackTrace")
                    error_msg = msg_el.text if msg_el is not None else None
                    error_stack = st_el.text if st_el is not None else None
            expected, actual = parse_assertion(error_msg, error_stack)
            http = parse_http(test_name, error_msg, error_stack)
            results.append(NormalizedFailure(
                id=make_failure_id("mstest", "mstest", test_name, "mstest"),
                framework="mstest",
                suite="mstest",
                title=test_name,
                file="mstest",
                duration_ms=duration_ms,
                status=status,
                error_message=error_msg,
                error_stack=error_stack,
                expected=expected,
                actual=actual,
                http=http,
                raw={"outcome": outcome},
            ))
        return results
