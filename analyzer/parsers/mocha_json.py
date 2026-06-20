"""Mocha JSON reporter parser."""
from __future__ import annotations
import json
import re
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http

# Mocha top-level arrays: "passes": [...], "failures": [...], "pending": [...]
_MOCHA_PASSES_RE = re.compile(r'"passes"\s*:\s*\[')
_MOCHA_FAILURES_RE = re.compile(r'"failures"\s*:\s*\[')
_MOCHA_PENDING_RE = re.compile(r'"pending"\s*:\s*\[')


class MochaJsonParser(Parser):
    """Parses Mocha --reporter=json output.
    Sniff: 'passes' + 'failures' + 'pending' as flat arrays (not nested suites)."""
    framework = "mocha"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        # Mocha JSON has flat 'passes', 'failures', 'pending' as top-level arrays.
        # Cypress also has these keys but as integer counts inside "stats" — distinguish
        # by requiring the values to be arrays (i.e. "passes": [).
        return (
            bool(_MOCHA_PASSES_RE.search(text)) and
            bool(_MOCHA_FAILURES_RE.search(text)) and
            bool(_MOCHA_PENDING_RE.search(text))
        )

    @classmethod
    def _parse_test(cls, test: dict, status: str) -> NormalizedFailure:
        title = test.get("fullTitle") or test.get("title", "")
        file_path = test.get("file", "unknown")
        suite = test.get("titlePath", [title])[0] if test.get("titlePath") else title.rsplit(" ", 1)[0]
        err = test.get("err") or {}
        error_msg = err.get("message")
        error_stack = err.get("stack")
        expected, actual = parse_assertion(error_msg, error_stack)
        http = parse_http(title, error_msg, error_stack)
        return NormalizedFailure(
            id=make_failure_id("mocha", suite, title, file_path),
            framework="mocha",
            suite=suite,
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
        )

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for test in data.get("passes", []):
            results.append(cls._parse_test(test, "passed"))
        for test in data.get("failures", []):
            results.append(cls._parse_test(test, "failed"))
        for test in data.get("pending", []):
            results.append(cls._parse_test(test, "skipped"))
        return results
