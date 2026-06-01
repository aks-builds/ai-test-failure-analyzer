"""Playwright JSON reporter parser.

Playwright emits a single JSON file with shape:
    { "config": {...}, "suites": [ { "title", "specs": [ { "title", "tests": [...] } ] } ], "stats": {...} }

Playwright error messages don't carry the URL — it lives in the spec source.
So when we have a file+line, we sniff a few surrounding lines to pull the
``request.get('/path')`` / ``request.post('/path')`` call out.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..security import cap_raw_record, safe_path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http

# Strip ANSI escapes from Playwright error messages (they include color codes by default).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Common Playwright API-test request shapes
_REQUEST_CALL_RE = re.compile(
    r"\.\s*(get|post|put|patch|delete|head)\s*\(\s*[\"'`]([^\"'`]+)[\"'`]",
    re.IGNORECASE,
)


def _strip_ansi(s: str | None) -> str | None:
    return _ANSI_RE.sub("", s) if s else s


def _sniff_endpoint_from_spec(spec_file: str, line: int | None) -> tuple[str | None, str | None]:
    """Read ±10 lines around ``line`` in the spec file to find the request URL/method.

    Returns ``(method, url)`` or ``(None, None)`` if not found / file unreadable.
    Safe against missing files and binary content.
    """
    if not spec_file or not line:
        return None, None
    try:
        p = Path(spec_file)
        if not p.is_absolute():
            p = Path.cwd() / p
        if not p.exists() or not p.is_file():
            return None, None
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return None, None

    start = max(0, line - 12)
    end = min(len(lines), line + 2)
    window = "".join(lines[start:end])
    m = _REQUEST_CALL_RE.search(window)
    if not m:
        return None, None
    return m.group(1).upper(), m.group(2)


class PlaywrightJsonParser(Parser):
    framework = "playwright"

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
        # Playwright JSON has "config" + "suites" + "specs" at the top level.
        # Cypress mochawesome shape has "results" instead, and uses "tests" not "specs".
        return '"config"' in s and '"suites"' in s and '"specs"' in s

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        out: list[NormalizedFailure] = []
        for suite in data.get("suites", []):
            cls._walk_suite(suite, suite.get("title", ""), out)
        return out

    @classmethod
    def _walk_suite(cls, suite: dict, suite_title: str, out: list[NormalizedFailure]) -> None:
        # Recurse into nested suites if present
        for child in suite.get("suites", []) or []:
            cls._walk_suite(child, f"{suite_title} > {child.get('title', '')}".strip(" >"), out)

        for spec in suite.get("specs", []) or []:
            spec_title = spec.get("title", "")
            spec_file = spec.get("file") or suite.get("file") or ""
            spec_line = spec.get("line")
            for test in spec.get("tests", []) or []:
                # Use the last attempt's result
                results = test.get("results", [])
                if not results:
                    continue
                result = results[-1]
                status_raw = result.get("status", "unknown")
                if status_raw == "passed":
                    status = "passed"
                elif status_raw == "skipped":
                    status = "skipped"
                elif test.get("status") == "flaky":
                    status = "flaky"
                else:
                    status = "failed"

                err = result.get("error") or {}
                err_msg = _strip_ansi(err.get("message"))
                err_stack = _strip_ansi(err.get("stack"))

                error_loc = result.get("errorLocation") or err.get("location") or {}
                file_path = error_loc.get("file") or spec_file
                line = error_loc.get("line") or spec_line

                # Attachments
                attachments = [
                    att.get("path", att.get("name", ""))
                    for att in result.get("attachments", []) or []
                ]

                expected, actual = parse_assertion(err_msg, err_stack)
                http = parse_http(spec_title, err_msg, err_stack)

                # Playwright errors rarely contain the request URL — sniff the spec source.
                if not http and status == "failed":
                    method, url = _sniff_endpoint_from_spec(file_path, line)
                    if url:
                        got_n = int(actual) if actual and actual.isdigit() else None
                        exp_n = int(expected) if expected and expected.isdigit() else None
                        http = {
                            "method": method,
                            "url": url,
                            "status_got": got_n,
                            "status_expected": exp_n,
                        }

                fail = NormalizedFailure(
                    id=make_failure_id(cls.framework, suite_title, spec_title, file_path),
                    framework=cls.framework,
                    suite=suite_title,
                    title=spec_title,
                    file=cls._relativize(file_path),
                    line=line,
                    duration_ms=result.get("duration"),
                    status=status,
                    error_message=err_msg,
                    error_stack=err_stack,
                    expected=expected,
                    actual=actual,
                    http=http,
                    attachments=attachments,
                    raw=cap_raw_record({
                        "spec": {k: v for k, v in spec.items() if k != "tests"},
                        "test": {k: v for k, v in test.items() if k != "results"},
                        "result": result,
                    }),
                )
                out.append(fail)

    @staticmethod
    def _relativize(path: str) -> str:
        """Strip absolute prefix when the path is inside CWD, for cleaner display."""
        if not path:
            return path
        try:
            return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
        except (ValueError, OSError):
            return path
