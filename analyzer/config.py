"""Runtime configuration. Secrets come from environment variables only.

Use ``settings()`` to access the singleton. Tokens are redacted in ``__repr__``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Analyzer configuration sourced from env vars and .env files."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ANALYZER_",
        case_sensitive=False,
        extra="ignore",
    )

    # Workspace
    workspace_root: Path = Field(default_factory=lambda: Path.cwd())

    # MCP HTTP transport
    http_host: str = "127.0.0.1"
    http_port: int = 8765
    http_token: SecretStr | None = None

    # Web UI
    web_host: str = "127.0.0.1"
    web_port: int = 8765

    # GitHub
    github_token: SecretStr | None = None
    github_repository: str | None = None  # "owner/repo"
    github_run_url: str | None = None

    # Behavior
    create_issue_default: bool = False
    non_interactive: bool = False


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Singleton accessor — instantiated once per process."""
    return Settings()


def reset_settings_cache() -> None:
    """Test hook: clear the cached settings (call after monkeypatching env vars)."""
    settings.cache_clear()


# Read GITHUB_TOKEN and GITHUB_REPOSITORY without the ANALYZER_ prefix as well,
# because GitHub Actions and gh CLI use the unprefixed names. We layer this on
# top of pydantic's env loading.
def github_token() -> str | None:
    import os

    s = settings()
    if s.github_token:
        return s.github_token.get_secret_value()
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def github_repository() -> str | None:
    import os

    s = settings()
    return s.github_repository or os.environ.get("GITHUB_REPOSITORY")
