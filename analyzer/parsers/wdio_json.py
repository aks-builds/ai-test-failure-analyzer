"""WebdriverIO native JSON reporter parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class WdioJsonParser(Parser):
    """Parses WebdriverIO JSON reporter output.
    Sniff: 'runner' + 'capabilities' + 'suites' keys."""
    framework = "wdio"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"runner"' in text and '"capabilities"' in text and '"suites"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for suite in data.get("suites", []):
            suite_name = suite.get("name", "")
            for test in suite.get("tests", []):
                raw_state = test.get("state", "unknown")
                status = "failed" if raw_state == "failed" else (
                    "skipped" if raw_state == "skipped" else "passed"
                )
                title = test.get("name", "")
                file_path = test.get("file", "unknown")
                err = test.get("error") or {}
                error_msg = err.get("message")
                error_stack = err.get("stack")
                expected, actual = parse_assertion(error_msg, error_stack)
                http = parse_http(title, error_msg, error_stack)
                results.append(NormalizedFailure(
                    id=make_failure_id("wdio", suite_name, title, file_path),
                    framework="wdio",
                    suite=suite_name,
                    title=title,
                    file=file_path,
                    duration_ms=test.get("duration"),
                    status=status,
                    error_message=error_msg,
                    error_stack=error_stack,
                    expected=expected,
                    actual=actual,
                    http=http,
                    raw=test,
                ))
        return results
