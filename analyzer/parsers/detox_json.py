"""Detox (React Native) JSON reporter parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class DetoxJsonParser(Parser):
    """Parses Detox test runner JSON output.
    Sniff: 'testResults' + 'device' + 'artifactsLocation' keys."""
    framework = "detox"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"artifactsLocation"' in text and '"device"' in text and '"testResults"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for file_result in data.get("testResults", []):
            file_path = file_result.get("testFilePath", "unknown")
            for assertion in file_result.get("assertionResults", []):
                raw_status = assertion.get("status", "unknown")
                status = "failed" if raw_status == "failed" else (
                    "skipped" if raw_status in ("pending", "todo") else "passed"
                )
                suite = " > ".join(assertion.get("ancestorTitles", []))
                title = assertion.get("title", "")
                err_msgs = assertion.get("failureMessages", [])
                error_msg = err_msgs[0] if err_msgs else None
                expected, actual = parse_assertion(error_msg, None)
                http = parse_http(title, error_msg, None)
                results.append(NormalizedFailure(
                    id=make_failure_id("detox", suite, title, file_path),
                    framework="detox",
                    suite=suite or file_path,
                    title=title,
                    file=file_path,
                    duration_ms=assertion.get("duration"),
                    status=status,
                    error_message=error_msg,
                    expected=expected,
                    actual=actual,
                    http=http,
                    raw={k: v for k, v in assertion.items() if k != "failureMessages"},
                ))
        return results
