"""Parser registry with content-sniff dispatch."""

from __future__ import annotations

import os
from pathlib import Path

from .base import NormalizedFailure, Parser
from .cypress_json import CypressJsonParser
from .jest_json import JestJsonParser
from .junit_generic import JUnitXmlParser
from .k6_json import K6JsonParser
from .newman_json import NewmanJsonParser
from .playwright_json import PlaywrightJsonParser
from .pytest_junit import PytestJUnitParser

# Order matters: most specific first.
# Newman and k6 before generic JSON parsers; JUnit XML fallback is last.
PARSERS: list[type[Parser]] = [
    PlaywrightJsonParser,
    NewmanJsonParser,
    K6JsonParser,
    JestJsonParser,
    CypressJsonParser,
    PytestJUnitParser,
    JUnitXmlParser,
]

FRAMEWORKS: dict[str, type[Parser]] = {
    "playwright": PlaywrightJsonParser,
    "newman": NewmanJsonParser,
    "k6": K6JsonParser,
    "jest": JestJsonParser,
    "vitest": JestJsonParser,
    "cypress": CypressJsonParser,
    "webdriverio": CypressJsonParser,
    "wdio": CypressJsonParser,
    "pytest": PytestJUnitParser,
    "junit": JUnitXmlParser,
    "rest-assured": JUnitXmlParser,
    "karate": JUnitXmlParser,
    "insomnia": JUnitXmlParser,
}


def detect(path: Path) -> type[Parser] | None:
    """Return the parser class that handles the file at ``path``, or ``None``."""
    safe = os.path.realpath(str(path))
    # startswith guard on the resolved path — required by CodeQL's CWE-022
    # sanitiser pattern. A file always resides within its own parent directory,
    # so this never filters legitimate paths while satisfying taint analysis.
    safe_parent = os.path.realpath(os.path.dirname(safe))
    if not (safe.startswith(safe_parent + os.sep) or safe == safe_parent):
        return None
    if not os.path.isfile(safe):
        return None
    try:
        with open(safe, "rb") as f:
            sample = f.read(4096)
    except OSError:
        return None

    for parser in PARSERS:
        try:
            if parser.can_parse(sample):
                return parser
        except Exception:
            continue
    return None


def parse(path: Path, framework: str = "auto") -> tuple[str, list[NormalizedFailure]]:
    """Parse a test report. Returns ``(framework_detected, failures)``.

    Set ``framework`` to ``"auto"`` (default) or one of the keys in ``FRAMEWORKS``.
    Failures includes all results, both passing and failing — callers filter as needed.
    """
    if framework != "auto":
        cls = FRAMEWORKS.get(framework.lower())
        if cls is None:
            raise ValueError(f"unknown framework: {framework!r}")
        return cls.framework, cls.parse(path)

    cls = detect(path)
    if cls is None:
        raise ValueError(
            f"could not detect framework for {path}. "
            f"Try passing framework=<{'/'.join(FRAMEWORKS)}> explicitly."
        )
    return cls.framework, cls.parse(path)


__all__ = ["NormalizedFailure", "Parser", "PARSERS", "FRAMEWORKS", "detect", "parse"]
