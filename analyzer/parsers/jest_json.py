"""Jest / Vitest JSON reporter parser.

Jest's ``--json`` output and Vitest's ``--reporter=json`` produce essentially
the same shape:

    {
      "numTotalTests": int,
      "testResults": [
        {
          "name": "<file path>",
          "assertionResults": [
            { "title", "status", "ancestorTitles": [...], "failureMessages": [...] }
          ]
        }
      ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path

from ..security import cap_raw_record
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class JestJsonParser(Parser):
    framework = "jest"

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
        # Jest signal
        return ('"testResults"' in s and '"assertionResults"' in s) or (
            '"numTotalTests"' in s and '"testResults"' in s
        )

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        out: list[NormalizedFailure] = []
        for file_result in data.get("testResults", []) or []:
            file_path = file_result.get("name", "")
            for assertion in file_result.get("assertionResults", []) or []:
                title = assertion.get("title", "")
                suite_parts = assertion.get("ancestorTitles", []) or []
                suite = " > ".join(suite_parts)

                status_raw = assertion.get("status", "")
                status = {
                    "passed": "passed",
                    "failed": "failed",
                    "pending": "skipped",
                    "skipped": "skipped",
                    "todo": "skipped",
                }.get(status_raw, "failed")

                failure_messages = assertion.get("failureMessages", []) or []
                err_blob = "\n".join(failure_messages) if failure_messages else None
                err_msg = failure_messages[0].splitlines()[0] if failure_messages else None
                err_stack = err_blob

                expected, actual = parse_assertion(err_msg, err_stack)
                http = parse_http(title, err_msg, err_stack)

                location = assertion.get("location") or {}
                line = location.get("line")

                duration = assertion.get("duration")

                out.append(
                    NormalizedFailure(
                        id=make_failure_id(cls.framework, suite, title, file_path),
                        framework=cls.framework,
                        suite=suite,
                        title=title,
                        file=file_path,
                        line=line,
                        duration_ms=int(duration) if duration else None,
                        status=status,  # type: ignore[arg-type]
                        error_message=err_msg,
                        error_stack=err_stack,
                        expected=expected,
                        actual=actual,
                        http=http,
                        attachments=[],
                        raw=cap_raw_record(assertion),
                    )
                )
        return out
