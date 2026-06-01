"""pytest output parser.

Supports both ``pytest --junitxml=results.xml`` and
``pytest --json-report --json-report-file=results.json`` (pytest-json-report).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..security import cap_raw_record
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http
from .junit_generic import read_junit


class PytestJUnitParser(Parser):
    framework = "pytest"

    @classmethod
    def can_parse(cls, sample: str | bytes) -> bool:
        if isinstance(sample, bytes):
            try:
                sample = sample.decode("utf-8", errors="replace")
            except Exception:
                return False
        s = sample.lstrip()
        # pytest-json-report shape
        if s.startswith("{") and '"created"' in s and '"tests"' in s and ('"outcome"' in s or '"summary"' in s):
            return True
        # pytest JUnit XML — heuristic: the testsuite element has python-like file paths or "pytest" mention
        if s.startswith("<?xml") and ("<testsuite" in s or "<testsuites" in s):
            # pytest typically writes classname with dotted python module paths
            if "tests/" in s or "classname=" in s:
                return True
        return False

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        # Sniff: JSON or XML?
        with open(path, "rb") as f:
            head = f.read(64).lstrip()
        if head.startswith(b"{"):
            return cls._parse_json(path)
        return read_junit(path, framework=cls.framework)

    @classmethod
    def _parse_json(cls, path: Path) -> list[NormalizedFailure]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        out: list[NormalizedFailure] = []
        for test in data.get("tests", []) or []:
            nodeid = test.get("nodeid", "")
            # nodeid is "path/to/file.py::TestClass::test_name"
            parts = nodeid.split("::")
            file = parts[0]
            title = parts[-1] if parts else nodeid
            suite = "::".join(parts[1:-1]) if len(parts) > 2 else ""

            outcome = test.get("outcome", "")
            status = {
                "passed": "passed",
                "failed": "failed",
                "skipped": "skipped",
                "xfailed": "passed",
                "xpassed": "passed",
                "error": "failed",
            }.get(outcome, "failed")

            call = test.get("call") or test.get("setup") or {}
            err_msg = call.get("longrepr") or test.get("longrepr")
            err_stack = call.get("crash", {}).get("traceback") if isinstance(call.get("crash"), dict) else None
            if isinstance(err_stack, list):
                err_stack = "\n".join(str(x) for x in err_stack)

            expected, actual = parse_assertion(err_msg, err_stack)
            http = parse_http(title, err_msg, err_stack)

            duration = test.get("duration") or call.get("duration")
            duration_ms = int(float(duration) * 1000) if duration else None

            out.append(
                NormalizedFailure(
                    id=make_failure_id(cls.framework, suite, title, file),
                    framework=cls.framework,
                    suite=suite,
                    title=title,
                    file=file,
                    line=call.get("lineno"),
                    duration_ms=duration_ms,
                    status=status,  # type: ignore[arg-type]
                    error_message=err_msg if isinstance(err_msg, str) else (str(err_msg) if err_msg else None),
                    error_stack=err_stack,
                    expected=expected,
                    actual=actual,
                    http=http,
                    attachments=[],
                    raw=cap_raw_record(test),
                )
            )
        return out
