"""Bounded log file scanner.

Looks for ERROR / FATAL / WARN / Exception / Traceback lines in *.log files.
Bounded by total bytes scanned and lines returned to avoid runaway costs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..security import (
    MAX_FILE_BYTES,
    MAX_RECURSION_DEPTH,
    MAX_TOTAL_SCAN_BYTES,
    safe_path,
    truncate_bytes,
)

LOG_LEVEL_RE = re.compile(r"\b(ERROR|FATAL|CRITICAL|WARN(?:ING)?|Exception|Traceback)\b", re.IGNORECASE)

EXCLUDE_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache"}


def _iter_log_files(root: Path, paths: list[str] | None, depth: int = 0) -> list[Path]:
    if paths:
        out: list[Path] = []
        for p in paths:
            try:
                resolved = safe_path(root, p)
                if resolved.is_file():
                    out.append(resolved)
                elif resolved.is_dir():
                    out.extend(_iter_log_files(resolved, None, depth=depth + 1))
            except Exception:
                continue
        return out

    if depth > MAX_RECURSION_DEPTH:
        return []

    out = []
    try:
        for entry in root.iterdir():
            if entry.name.startswith(".") and entry.name not in (".env",):
                continue
            if entry.is_dir():
                if entry.name in EXCLUDE_DIRS:
                    continue
                out.extend(_iter_log_files(entry, None, depth=depth + 1))
            elif entry.is_file() and entry.suffix == ".log":
                out.append(entry)
    except (OSError, PermissionError):
        pass
    return out


def scan_logs(
    workspace: Path,
    paths: list[str] | None = None,
    max_bytes: int = MAX_TOTAL_SCAN_BYTES,
    max_matches_per_file: int = 50,
) -> dict[str, Any]:
    """Scan log files for error-level lines. Returns evidence-shaped dict."""
    workspace = Path(workspace).resolve()
    files = _iter_log_files(workspace, paths)

    total_bytes = 0
    matches = []
    scanned: list[str] = []

    for f in files:
        try:
            size = f.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            scanned.append(f"{f.relative_to(workspace) if _is_subpath(f, workspace) else f} (skipped: {size} bytes > cap)")
            continue
        if total_bytes + size > max_bytes:
            break

        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        total_bytes += size
        rel = str(f.relative_to(workspace) if _is_subpath(f, workspace) else f)
        scanned.append(rel)

        per_file_hits = 0
        for i, line in enumerate(lines, start=1):
            m = LOG_LEVEL_RE.search(line)
            if not m:
                continue
            level = m.group(1).upper()
            matches.append({
                "file": rel,
                "line_no": i,
                "level": level,
                "text": truncate_bytes(line.rstrip()),
            })
            per_file_hits += 1
            if per_file_hits >= max_matches_per_file:
                break

    return {
        "available": bool(files),
        "scanned_files": scanned,
        "matches": matches,
        "summary": {
            "files_scanned": len(scanned),
            "match_count": len(matches),
            "bytes_scanned": total_bytes,
        },
    }


def _is_subpath(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False
