"""ParserRegistry — internal registry for all framework parsers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from .base import NormalizedFailure, Parser


class ParserRegistry:
    """Registry of all Parser subclasses. Order = detection priority (most specific first)."""

    _parsers: ClassVar[list[type[Parser]]] = []
    _frameworks: ClassVar[dict[str, type[Parser]]] = {}

    @classmethod
    def register(cls, parser: type[Parser], aliases: list[str] | None = None) -> None:
        """Register a parser class and optional framework-name aliases."""
        cls._parsers.append(parser)
        cls._frameworks[parser.framework] = parser
        for alias in (aliases or []):
            cls._frameworks[alias.lower()] = parser

    @classmethod
    def detect(cls, path: Path) -> type[Parser] | None:
        """Return the parser class that handles the file at ``path``, or ``None``."""
        safe = os.path.realpath(str(path))
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
        for parser in cls._parsers:
            try:
                if parser.can_parse(sample):
                    return parser
            except Exception:
                continue
        return None

    @classmethod
    def parse(cls, path: Path, framework: str = "auto") -> tuple[str, list[NormalizedFailure]]:
        """Parse a test report via the registry.

        Set ``framework`` to ``"auto"`` (default) or one of the registered framework names.
        Returns ``(framework_detected, failures)``.
        """
        if framework != "auto":
            pcls = cls._frameworks.get(framework.lower())
            if pcls is None:
                raise ValueError(f"unknown framework: {framework!r}")
            return pcls.framework, pcls.parse(path)
        pcls = cls.detect(path)
        if pcls is None:
            raise ValueError(
                f"could not detect framework for {path}. "
                f"Pass framework= explicitly. Known: {sorted(cls._frameworks)}"
            )
        return pcls.framework, pcls.parse(path)
