"""Output renderers — Markdown for issues/web, ANSI for terminal."""

from .ansi import render_ansi_report
from .markdown import render_markdown_report

__all__ = ["render_markdown_report", "render_ansi_report"]
