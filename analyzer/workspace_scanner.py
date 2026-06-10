# analyzer/workspace_scanner.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SOURCE_DIR_NAMES = {"src", "app", "lib", "api", "source", "backend", "server"}
TEST_DIR_NAMES = {"tests", "test", "spec", "specs", "e2e", "__tests__"}
NOISE_DIR_NAMES = {"fixtures", "__mocks__", "__fixtures__", "testdata", "test-data", "mocks"}
OPENAPI_FILENAMES = {"openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml", "swagger.yml", "swagger.json"}
NOISE_KEYWORDS: set[str] = {"intentional", "on purpose", "expected to fail", "demo", "deliberately"}


@dataclass
class WorkspaceProfile:
    mode: Literal["FULL_SOURCE", "API_ONLY"]
    source_roots: list[Path] = field(default_factory=list)
    test_roots: list[Path] = field(default_factory=list)
    noise_paths: list[Path] = field(default_factory=list)
    openapi_spec: Path | None = None
    has_git: bool = False
    noise_keywords: set[str] = field(default_factory=lambda: set(NOISE_KEYWORDS))


def scan_workspace(root: Path, force_api_only: bool = False) -> WorkspaceProfile:
    """Scan workspace root and return a WorkspaceProfile.

    Args:
        root: Workspace root directory (will be resolved to absolute).
        force_api_only: When True, always returns API_ONLY regardless of directory layout.
    """
    root = root.resolve()
    source_roots: list[Path] = []
    test_roots: list[Path] = []
    noise_paths: list[Path] = []
    openapi_spec: Path | None = None

    try:
        children = list(root.iterdir())
    except OSError:
        children = []

    for child in children:
        name = child.name.lower()
        if child.is_dir():
            if name in SOURCE_DIR_NAMES:
                source_roots.append(child)
            elif name in TEST_DIR_NAMES:
                test_roots.append(child)
                for sub in child.rglob("*"):
                    if sub.is_dir() and sub.name.lower() in NOISE_DIR_NAMES:
                        noise_paths.append(sub)
        elif child.is_file() and openapi_spec is None and name in OPENAPI_FILENAMES:
            openapi_spec = child

    # Also check docs/ and api/ subdirs for OpenAPI spec
    if openapi_spec is None:
        for search_base in [root / "docs", root / "api"]:
            if search_base.is_dir():
                for fname in OPENAPI_FILENAMES:
                    candidate = search_base / fname
                    if candidate.exists():
                        openapi_spec = candidate
                        break
            if openapi_spec:
                break

    has_git = (root / ".git").exists()

    # Load optional custom noise keywords from .atfa/noise-keywords.json
    noise_keywords: set[str] = set(NOISE_KEYWORDS)
    custom_kw = root / ".atfa" / "noise-keywords.json"
    if custom_kw.exists():
        try:
            extra = json.loads(custom_kw.read_text(encoding="utf-8"))
            if isinstance(extra, list):
                noise_keywords.update(str(k).lower() for k in extra)
        except Exception:
            pass

    mode: Literal["FULL_SOURCE", "API_ONLY"] = (
        "API_ONLY" if force_api_only or not source_roots else "FULL_SOURCE"
    )

    return WorkspaceProfile(
        mode=mode,
        source_roots=source_roots,
        test_roots=test_roots,
        noise_paths=noise_paths,
        openapi_spec=openapi_spec,
        has_git=has_git,
        noise_keywords=noise_keywords,
    )
