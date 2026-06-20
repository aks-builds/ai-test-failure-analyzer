"""RSpec JSON formatter parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class RSpecJsonParser(Parser):
    """Parses RSpec --format json output.
    Sniff: 'version' + 'examples' + 'summary_line'."""
    framework = "rspec"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"summary_line"' in text and '"examples"' in text and '"version"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for ex in data.get("examples", []):
            raw_status = ex.get("status", "unknown")
            status = "failed" if raw_status == "failed" else (
                "skipped" if raw_status == "pending" else "passed"
            )
            title = ex.get("full_description") or ex.get("description", "")
            file_path = ex.get("file_path", "unknown")
            exc = ex.get("exception") or {}
            error_msg = exc.get("message")
            expected, actual = parse_assertion(error_msg, None)
            http = parse_http(title, error_msg, None)
            results.append(NormalizedFailure(
                id=make_failure_id("rspec", ex.get("id", ""), title, file_path),
                framework="rspec",
                suite=file_path,
                title=title,
                file=file_path,
                line=ex.get("line_number"),
                duration_ms=int((ex.get("run_time") or 0) * 1000),
                status=status,
                error_message=error_msg,
                expected=expected,
                actual=actual,
                http=http,
                raw=ex,
            ))
        return results
