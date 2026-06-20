"""Go test -json (NDJSON) parser."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class GoTestJsonParser(Parser):
    """Parses `go test -json` NDJSON output (one JSON object per line).
    Sniff: first line contains '{"Action":'."""
    framework = "go"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        first_line = sample.split(b"\n")[0].strip()
        try:
            obj = json.loads(first_line)
            return "Action" in obj and "Package" in obj
        except (json.JSONDecodeError, ValueError):
            return False

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        # Accumulate output lines per test, emit on pass/fail action
        outputs: dict[str, list[str]] = defaultdict(list)
        results: list[NormalizedFailure] = []
        elapsed: dict[str, float] = {}

        with open(path, encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                action = event.get("Action", "")
                pkg = event.get("Package", "")
                test = event.get("Test")
                if not test:
                    continue  # package-level events
                key = f"{pkg}::{test}"
                if action == "output":
                    outputs[key].append(event.get("Output", ""))
                elif action in ("pass", "fail", "skip"):
                    elapsed[key] = event.get("Elapsed", 0)
                    status = "failed" if action == "fail" else (
                        "skipped" if action == "skip" else "passed"
                    )
                    error_msg = "".join(outputs.get(key, [])).strip() or None
                    expected, actual = parse_assertion(error_msg, None)
                    http = parse_http(test, error_msg, None)
                    results.append(NormalizedFailure(
                        id=make_failure_id("go", pkg, test, pkg),
                        framework="go",
                        suite=pkg,
                        title=test,
                        file=pkg,
                        duration_ms=int(elapsed.get(key, 0) * 1000),
                        status=status,
                        error_message=error_msg,
                        expected=expected,
                        actual=actual,
                        http=http,
                        raw=event,
                    ))
        return results
