"""EvidenceBundle — what an EvidenceCollector returns."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .graph import EvidenceNode


@dataclass
class EvidenceBundle:
    """Result of one EvidenceCollector.collect() call."""
    collector_name: str
    tier: Literal["tier1", "tier2"]
    available: bool
    nodes: list["EvidenceNode"] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    legacy: dict = field(default_factory=dict)

    @classmethod
    def empty(cls, name: str, tier: Literal["tier1", "tier2"] = "tier1") -> "EvidenceBundle":
        return cls(
            collector_name=name,
            tier=tier,
            available=False,
            legacy={"available": False, "summary": {}},
        )
