"""CTRF (Common Test Results Format) universal schema parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class CTRFJsonParser(Parser):
    """Parses CTRF universal schema JSON.
    Sniff: 'results' + 'tool' + 'summary' top-level keys."""
    framework = "ctrf"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"results"' in text and '"tool"' in text and '"summary"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results_obj = data.get("results", {})
        tool = (results_obj.get("tool") or {}).get("name", "ctrf")
        results: list[NormalizedFailure] = []
        for test in results_obj.get("tests", []):
            raw_status = test.get("status", "unknown")
            status = "failed" if raw_status == "failed" else (
                "skipped" if raw_status == "skipped" else (
                    "flaky" if raw_status == "flaky" else "passed"
                )
            )
            title = test.get("name", "")
            file_path = test.get("filePath", "unknown")
            suite = test.get("suite", tool)
            error_msg = test.get("message")
            error_stack = test.get("trace")
            expected, actual = parse_assertion(error_msg, error_stack)
            http = parse_http(title, error_msg, error_stack)
            # Preserve CTRF-specific fields in ctrf_extra
            extra = {k: v for k, v in test.items()
                     if k not in ("name", "status", "duration", "message", "trace",
                                  "filePath", "suite")}
            results.append(NormalizedFailure(
                id=make_failure_id("ctrf", suite, title, file_path),
                framework="ctrf",
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
                ctrf_extra=extra,
                raw=test,
            ))
        return results
