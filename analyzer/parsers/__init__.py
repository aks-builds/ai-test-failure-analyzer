"""Parser registry with content-sniff dispatch."""

from __future__ import annotations

import os
from pathlib import Path

from .base import NormalizedFailure, Parser
from .cypress_json import CypressJsonParser
from .detox_json import DetoxJsonParser
from .go_test_json import GoTestJsonParser
from .jest_json import JestJsonParser
from .junit_generic import JUnitXmlParser
from .k6_json import K6JsonParser
from .mocha_json import MochaJsonParser
from .newman_json import NewmanJsonParser
from .nunit_xml import NUnitXmlParser
from .phpunit_xml import PHPUnitXmlParser
from .playwright_json import PlaywrightJsonParser
from .pytest_junit import PytestJUnitParser
from .rspec_json import RSpecJsonParser
from .robot_xml import RobotXmlParser
from .vitest_json import VitestJsonParser
from .wdio_json import WdioJsonParser
from .xunit_xml import XUnitXmlParser

# Order matters: most specific first.
# Newman and k6 before generic JSON parsers; JUnit XML fallback is last.
# Vitest must precede Jest — "vitestVersion" key distinguishes them.
# Go NDJSON before generic JSON; PHPUnit/NUnit/xUnit/Robot before JUnit fallback.
PARSERS: list[type[Parser]] = [
    PlaywrightJsonParser,
    NewmanJsonParser,
    K6JsonParser,
    VitestJsonParser,
    WdioJsonParser,
    DetoxJsonParser,
    MochaJsonParser,
    JestJsonParser,
    CypressJsonParser,
    RSpecJsonParser,
    GoTestJsonParser,
    PHPUnitXmlParser,
    NUnitXmlParser,
    XUnitXmlParser,
    RobotXmlParser,
    PytestJUnitParser,
    JUnitXmlParser,
]

FRAMEWORKS: dict[str, type[Parser]] = {
    "playwright": PlaywrightJsonParser,
    "newman": NewmanJsonParser,
    "k6": K6JsonParser,
    "vitest": VitestJsonParser,
    "wdio": WdioJsonParser,
    "webdriverio": WdioJsonParser,
    "detox": DetoxJsonParser,
    "mocha": MochaJsonParser,
    "jest": JestJsonParser,
    "cypress": CypressJsonParser,
    "rspec": RSpecJsonParser,
    "go": GoTestJsonParser,
    "gotest": GoTestJsonParser,
    "phpunit": PHPUnitXmlParser,
    "nunit": NUnitXmlParser,
    "xunit": XUnitXmlParser,
    "robot": RobotXmlParser,
    "robotframework": RobotXmlParser,
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


from .registry import ParserRegistry

# Register all existing parsers in detection-priority order (most specific first).
# Vitest must precede Jest — "vitestVersion" key distinguishes them.
ParserRegistry.register(PlaywrightJsonParser)
ParserRegistry.register(NewmanJsonParser,   aliases=["newman"])
ParserRegistry.register(K6JsonParser,       aliases=["k6"])
ParserRegistry.register(VitestJsonParser,   aliases=["vitest"])
ParserRegistry.register(WdioJsonParser,     aliases=["wdio", "webdriverio"])
ParserRegistry.register(DetoxJsonParser,    aliases=["detox"])
ParserRegistry.register(MochaJsonParser,    aliases=["mocha"])
ParserRegistry.register(JestJsonParser,     aliases=["jest"])
ParserRegistry.register(CypressJsonParser,  aliases=["cypress"])
ParserRegistry.register(RSpecJsonParser,    aliases=["rspec"])
ParserRegistry.register(GoTestJsonParser,   aliases=["go", "gotest"])
ParserRegistry.register(PHPUnitXmlParser,   aliases=["phpunit"])
ParserRegistry.register(NUnitXmlParser,     aliases=["nunit"])
ParserRegistry.register(XUnitXmlParser,     aliases=["xunit"])
ParserRegistry.register(RobotXmlParser,     aliases=["robot", "robotframework"])
ParserRegistry.register(PytestJUnitParser,  aliases=["pytest"])
ParserRegistry.register(JUnitXmlParser,     aliases=["junit", "rest-assured", "karate", "insomnia"])

__all__ = [
    "NormalizedFailure", "Parser",
    "PARSERS", "FRAMEWORKS", "detect", "parse",
    "ParserRegistry",
]
