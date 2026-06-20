"""EvidenceCollector — abstract base class all evidence collectors implement."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Literal

from .bundle import EvidenceBundle


class EvidenceCollector(ABC):
    """Collect one evidence source from a workspace."""

    name: ClassVar[str]
    tier: ClassVar[Literal["tier1", "tier2"]]

    @classmethod
    @abstractmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        """Return True if this collector can run in this workspace.
        Fast — only existence checks, no subprocess calls."""

    @classmethod
    @abstractmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        """Collect evidence. Must never raise — catch all exceptions internally."""
