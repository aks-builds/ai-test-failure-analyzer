"""Cypress / WebdriverIO JSON parser.

Both frameworks emit mochawesome-style JSON:

    {
      "stats": {...},
      "results": [
        {
          "file": "...",
          "suites": [ { "title", "tests": [ { "title", "state", "err": {...} } ], "suites": [...] } ]
        }
      ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path

from ..security import cap_raw_record
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class CypressJsonParser(Parser):
    framework = "cypress"

    @classmethod
    def can_parse(cls, sample: str | bytes) -> bool:
        if isinstance(sample, bytes):
            try:
                sample = sample.decode("utf-8", errors="replace")
            except Exception:
                return False
        s = sample.lstrip()
        if not s.startswith("{"):
            return False
        # mochawesome shape: results array with nested suites + tests with err object
        return '"stats"' in s and '"results"' in s and ('"suites"' in s or '"pending"' in s)

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        out: list[NormalizedFailure] = []
        for file_result in data.get("results", []) or []:
            file_path = file_result.get("file") or file_result.get("fullFile", "")
            for suite in file_result.get("suites", []) or []:
                cls._walk_suite(suite, suite.get("title", ""), file_path, out)
            # Some shapes attach tests directly to results
            for test in file_result.get("tests", []) or []:
                cls._emit_test(test, "", file_path, out)
        return out

    @classmethod
    def _walk_suite(cls, suite: dict, suite_title: str, file_path: str, out: list[NormalizedFailure]) -> None:
        for test in suite.get("tests", []) or []:
            cls._emit_test(test, suite_title, file_path, out)
        for child in suite.get("suites", []) or []:
            child_title = child.get("title", "")
            full = f"{suite_title} > {child_title}".strip(" >")
            cls._walk_suite(child, full, file_path, out)

    @classmethod
    def _emit_test(cls, test: dict, suite_title: str, file_path: str, out: list[NormalizedFailure]) -> None:
        title = test.get("title", "")
        state = test.get("state") or ("failed" if test.get("fail") else "passed" if test.get("pass") else "")
        status = {
            "passed": "passed",
            "failed": "failed",
            "pending": "skipped",
            "skipped": "skipped",
        }.get(state, "failed" if state else "skipped")

        err = test.get("err") or {}
        err_msg = err.get("message")
        err_stack = err.get("estack") or err.get("stack")
        expected, actual = parse_assertion(err_msg, err_stack)
        http = parse_http(title, err_msg, err_stack)

        duration = test.get("duration")

        out.append(
            NormalizedFailure(
                id=make_failure_id(cls.framework, suite_title, title, file_path),
                framework=cls.framework,
                suite=suite_title,
                title=title,
                file=file_path,
                line=None,
                duration_ms=int(duration) if duration else None,
                status=status,  # type: ignore[arg-type]
                error_message=err_msg,
                error_stack=err_stack,
                expected=expected,
                actual=actual,
                http=http,
                attachments=[],
                raw=cap_raw_record(test),
            )
        )
