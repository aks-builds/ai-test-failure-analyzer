"""Security primitives shared across the analyzer.

Every entry point that touches the filesystem, runs a subprocess, or accepts
external input flows through this module. The goal is defense in depth without
making the codebase paranoid — each guard documents what it protects against.
"""

from __future__ import annotations

import re
from pathlib import Path

# ── Size caps (per the threat model in the design plan) ──────────────────────
MAX_FILE_BYTES = 5 * 1024 * 1024          # 5 MB per file
MAX_TOTAL_SCAN_BYTES = 50 * 1024 * 1024   # 50 MB across a single scan call
MAX_LINE_BYTES = 4 * 1024                 # 4 KB per log line
MAX_GIT_COMMITS = 200
MAX_RECURSION_DEPTH = 6
MAX_RAW_RECORD_BYTES = 32 * 1024          # 32 KB cap on raw test records embedded in NormalizedFailure

# ── Whitelists ───────────────────────────────────────────────────────────────
GIT_ALLOWED_SUBCOMMANDS = frozenset({"log", "diff", "show", "rev-parse", "status", "ls-files"})
COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{7,40}$")


class SecurityError(ValueError):
    """Raised when an input violates a security guard. Never silently swallowed."""


def safe_path(root: str | Path, candidate: str | Path) -> Path:
    """Resolve ``candidate`` relative to ``root`` and ensure it stays inside.

    Protects against path traversal (``../../etc/passwd``) and symlinks pointing
    outside the workspace. Returns the resolved absolute path on success.
    """
    root_p = Path(root).resolve()
    cand_p = (root_p / candidate).resolve() if not Path(candidate).is_absolute() else Path(candidate).resolve()

    try:
        cand_p.relative_to(root_p)
    except ValueError as e:
        raise SecurityError(f"path '{candidate}' escapes workspace root '{root_p}'") from e

    # Reject symlinks whose target leaves the root (resolve() already followed them,
    # but the check above is on the resolved path — that is sufficient).
    return cand_p


def validate_git_args(args: list[str]) -> list[str]:
    """Ensure subprocess args start with an allowed git subcommand and contain no shell metacharacters.

    Raises ``SecurityError`` on any violation. Returns the same list on success
    so this can be used inline: ``subprocess.run(["git", *validate_git_args(a)])``.
    """
    if not args:
        raise SecurityError("empty git args")
    if args[0] not in GIT_ALLOWED_SUBCOMMANDS:
        raise SecurityError(f"git subcommand '{args[0]}' is not whitelisted")
    for a in args:
        if any(c in a for c in (";", "|", "&", "$", "`", "\n", "\r", "\x00")):
            raise SecurityError(f"shell metacharacter in arg: {a!r}")
    return args


def validate_commit_hash(h: str) -> str:
    """Return the hash if it looks valid; raise otherwise."""
    if not COMMIT_HASH_RE.match(h):
        raise SecurityError(f"not a valid commit hash: {h!r}")
    return h


def truncate_bytes(data: str, cap: int = MAX_LINE_BYTES, suffix: str = "…[truncated]") -> str:
    """Truncate ``data`` to at most ``cap`` bytes (when UTF-8 encoded)."""
    encoded = data.encode("utf-8", errors="replace")
    if len(encoded) <= cap:
        return data
    return encoded[: cap - len(suffix.encode())].decode("utf-8", errors="replace") + suffix


def cap_raw_record(record: dict, cap: int = MAX_RAW_RECORD_BYTES) -> dict:
    """Embed raw framework records in NormalizedFailure without unbounded growth.

    If the JSON-serialized form exceeds ``cap``, replace with a marker dict
    containing only the framework-agnostic essentials.
    """
    import json

    try:
        serialized = json.dumps(record, default=str)
    except (TypeError, ValueError):
        return {"__truncated__": True, "reason": "non-serializable"}

    if len(serialized) <= cap:
        return record
    return {
        "__truncated__": True,
        "original_bytes": len(serialized),
        "preview": serialized[: cap // 2] + "…",
    }


def strip_html(text: str) -> str:
    """Strip simple HTML tags to prevent injection into rendered Markdown."""
    return re.sub(r"<[^>]+>", "", text)
