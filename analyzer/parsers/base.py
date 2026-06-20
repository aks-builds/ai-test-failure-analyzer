"""Common schema and Parser ABC for all framework-specific parsers."""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Status = Literal["failed", "passed", "skipped", "flaky"]


@dataclass
class HttpAssertion:
    method: str | None = None
    url: str | None = None
    status_got: int | None = None
    status_expected: int | None = None


@dataclass
class NormalizedFailure:
    """Framework-agnostic representation of one test result.

    Stable across Playwright, pytest, Jest/Vitest, and Cypress/WebdriverIO so
    downstream analysis works uniformly. The ``raw`` dict preserves the
    framework-specific record (size-capped) for any consumer that wants more.
    """

    id: str
    framework: str
    suite: str
    title: str
    file: str
    line: int | None = None
    duration_ms: int | None = None
    status: Status = "failed"
    error_message: str | None = None
    error_stack: str | None = None
    expected: str | None = None
    actual: str | None = None
    http: dict | None = None
    attachments: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    # v2 intelligence fields — backward compatible, all default to None / empty
    flakiness_score: float | None = None
    flakiness_category: str | None = None
    ctrf_extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_failure_id(framework: str, suite: str, title: str, file: str) -> str:
    """Deterministic hash for cross-run identity. Stable as long as suite+title+file are stable."""
    seed = f"{framework}::{suite}::{title}::{file}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


# ── Assertion-extraction helpers ─────────────────────────────────────────────
_EXPECT_TOBE_RE = re.compile(
    r"expect\(([^)]+)\)\.toBe\(([^)]+)\)|Expected:\s*([^\n]+)\s*Received:\s*([^\n]+)",
    re.IGNORECASE,
)
_PY_ASSERT_EQ_RE = re.compile(
    r"assert\s+(?P<lhs>[^=]+?)==\s*(?P<rhs>.+?)$|AssertionError:\s*(?P<msg>.+)$",
    re.MULTILINE,
)
_HTTP_STATUS_RE = re.compile(r"\b(\d{3})\b")
_URL_RE = re.compile(r"(?:GET|POST|PUT|PATCH|DELETE|HEAD)\s+(\S+)", re.IGNORECASE)


def parse_assertion(error_message: str | None, error_stack: str | None) -> tuple[str | None, str | None]:
    """Best-effort (expected, actual) extraction from assertion errors.

    Tries the strongest signal first: "Expected: X\nReceived: Y" (Playwright, Jest,
    Vitest, Cypress all emit this). Falls back to pytest-style and toBe-style patterns.
    """
    blob = "\n".join(filter(None, (error_message, error_stack))) or ""
    if not blob:
        return None, None

    # Most reliable across JS test frameworks
    exp_m = re.search(r"Expected:\s*([^\n]+)", blob)
    act_m = re.search(r"Received:\s*([^\n]+)", blob)
    if not act_m:
        act_m = re.search(r"Actual:\s*([^\n]+)", blob)
    if exp_m and act_m:
        return exp_m.group(1).strip(), act_m.group(1).strip()

    # Python: `assert X == Y` form
    py = _PY_ASSERT_EQ_RE.search(blob)
    if py and py.group("lhs") and py.group("rhs"):
        return py.group("rhs").strip(), py.group("lhs").strip()

    # toBe(value) form — only useful when the captured value isn't a placeholder word
    m = _EXPECT_TOBE_RE.search(blob)
    if m and m.group(2):
        val = m.group(2).strip()
        if val.lower() not in ("expected", "received", "actual"):
            return val, None
    return None, None


def parse_http(test_title: str, error_message: str | None, error_stack: str | None) -> dict | None:
    """Best-effort HTTP assertion extraction. Returns ``None`` if not an API test."""
    blob = "\n".join(filter(None, (test_title, error_message, error_stack))) or ""
    url_m = _URL_RE.search(blob)
    if not url_m:
        return None

    expected_s, actual_s = parse_assertion(error_message, error_stack)
    got = exp = None
    if expected_s and _HTTP_STATUS_RE.fullmatch(expected_s):
        exp = int(expected_s)
    if actual_s and _HTTP_STATUS_RE.fullmatch(actual_s):
        got = int(actual_s)

    method_m = re.search(r"(GET|POST|PUT|PATCH|DELETE|HEAD)", blob, re.IGNORECASE)
    return {
        "method": method_m.group(1).upper() if method_m else None,
        "url": url_m.group(1),
        "status_got": got,
        "status_expected": exp,
    }


class Parser(ABC):
    """Abstract parser. Subclasses parse one framework's output into NormalizedFailure objects."""

    framework: str  # set by subclass

    @classmethod
    @abstractmethod
    def can_parse(cls, sample: str | bytes) -> bool:
        """Sniff a 4 KB sample; return True if this parser handles it."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        """Parse the report file at ``path`` into normalized failure records."""
        raise NotImplementedError
