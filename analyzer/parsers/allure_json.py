"""Allure results JSON parser (single-result file format)."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class AllureJsonParser(Parser):
    """Parses a single Allure result JSON file.
    Sniff: 'uuid' + 'testCaseId' + 'labels' keys at top level."""
    framework = "allure"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"uuid"' in text and '"testCaseId"' in text and '"labels"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Allure can be a single object or an array
        items = data if isinstance(data, list) else [data]
        results: list[NormalizedFailure] = []
        for item in items:
            raw_status = item.get("status", "unknown")
            status = "failed" if raw_status == "failed" else (
                "skipped" if raw_status in ("skipped", "broken") else "passed"
            )
            title = item.get("name") or item.get("fullName", "")
            suite = next(
                (lbl["value"] for lbl in item.get("labels", []) if lbl.get("name") == "suite"),
                item.get("fullName", "unknown").rsplit("#", 1)[0],
            )
            details = item.get("statusDetails") or {}
            error_msg = details.get("message")
            error_stack = details.get("trace")
            expected, actual = parse_assertion(error_msg, error_stack)
            http = parse_http(title, error_msg, error_stack)
            start = item.get("start", 0)
            stop = item.get("stop", start)
            results.append(NormalizedFailure(
                id=item.get("uuid") or make_failure_id("allure", suite, title, suite),
                framework="allure",
                suite=suite,
                title=title,
                file=suite,
                duration_ms=stop - start,
                status=status,
                error_message=error_msg,
                error_stack=error_stack,
                expected=expected,
                actual=actual,
                http=http,
                raw=item,
            ))
        return results
