"""Configuration / environment / deployment-artifact scanner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..security import MAX_FILE_BYTES, truncate_bytes

CONFIG_PATTERNS = [
    ".env",
    ".env.example",
    ".env.local",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
    "CHANGELOG.md",
    "RELEASES.md",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "playwright.config.ts",
    "playwright.config.js",
    "jest.config.js",
    "jest.config.ts",
    "vitest.config.ts",
    "cypress.config.ts",
    "cypress.config.js",
    "wdio.conf.ts",
    "wdio.conf.js",
]


def _safe_read(path: Path, max_bytes: int = MAX_FILE_BYTES) -> str | None:
    try:
        size = path.stat().st_size
        if size > max_bytes:
            return f"…[file too large: {size} bytes]"
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        return truncate_bytes(content, cap=max_bytes // 4)
    except OSError:
        return None


def _redact_env(content: str) -> str:
    """Mask values that look like secrets in .env files before exposing them."""
    out_lines = []
    for line in content.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            kl = k.lower().strip()
            if any(s in kl for s in ("token", "secret", "key", "password", "passwd")):
                v_show = "***REDACTED***"
            else:
                v_show = v
            out_lines.append(f"{k}={v_show}")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def scan_config(workspace: Path) -> dict[str, Any]:
    """Read common config and changelog files. Returns evidence-shaped dict."""
    workspace = Path(workspace).resolve()
    found: list[dict[str, Any]] = []

    for name in CONFIG_PATTERNS:
        path = workspace / name
        if not path.exists() or not path.is_file():
            continue
        content = _safe_read(path)
        if content is None:
            continue
        if name.startswith(".env"):
            content = _redact_env(content)
        found.append({
            "path": name,
            "size_bytes": path.stat().st_size,
            "excerpt": content,
        })

    return {
        "available": bool(found),
        "files": found,
        "summary": {"count": len(found)},
    }
