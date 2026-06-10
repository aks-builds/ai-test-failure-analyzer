"""Parser registry with content-sniff dispatch.

Use ``detect(path)`` to find the right parser, or ``parse(path, framework='auto')``
to do everything in one call.
"""

from __future__ import annotations

from pathlib import Path

from .base import NormalizedFailure, Parser
from .cypress_json import CypressJsonParser
from .jest_json import JestJsonParser
from .junit_generic import JUnitXmlParser
from .newman_json import NewmanJsonParser
from .playwright_json import PlaywrightJsonParser
from .pytest_junit import PytestJUnitParser

# Order matters: more specific parsers come first.
# Newman before generic JSON parsers; PlaywrightJsonParser must come before
# generic JUnit because both can match XML.
PARSERS: list[type[Parser]] = [
    PlaywrightJsonParser,
    NewmanJsonParser,
    JestJsonParser,
    CypressJsonParser,
    PytestJUnitParser,
    JUnitXmlParser,
]

FRAMEWORKS: dict[str, type[Parser]] = {
    "playwright": PlaywrightJsonParser,
    "newman": NewmanJsonParser,
    "jest": JestJsonParser,
    "vitest": JestJsonParser,
    "cypress": CypressJsonParser,
    "webdriverio": CypressJsonParser,
    "wdio": CypressJsonParser,
    "pytest": PytestJUnitParser,
    "junit": JUnitXmlParser,
}


def detect(path: Path) -> type[Parser] | None:
    """Return the parser class that handles the file at ``path``, or ``None``."""
    try:
        with open(path, "rb") as f:
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
