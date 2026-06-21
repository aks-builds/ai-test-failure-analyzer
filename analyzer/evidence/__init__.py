"""Evidence collectors: read git history, scan logs, scan config files, correlate."""

from .config_scan import scan_config
from .correlator import correlate, cluster_failures
from .git_scan import scan_git_history
from .log_scan import scan_logs

from .bundle import EvidenceBundle
from .collector import EvidenceCollector
from .graph import EvidenceEdge, EvidenceGraph, EvidenceNode
from .registry import EvidenceRegistry
from .collectors.git_collector import GitCollector
from .collectors.log_collector import LogCollector
from .collectors.config_collector import ConfigCollector
from .collectors.dep_diff_collector import DepDiffCollector

# Module-level shared registry — pre-registered with the three core collectors
_REGISTRY = EvidenceRegistry()
_REGISTRY.register(GitCollector)
_REGISTRY.register(LogCollector)
_REGISTRY.register(ConfigCollector)
_REGISTRY.register(DepDiffCollector)

__all__ = [
    "scan_config", "scan_git_history", "scan_logs", "correlate", "cluster_failures",
    "EvidenceBundle", "EvidenceCollector",
    "EvidenceEdge", "EvidenceGraph", "EvidenceNode",
    "EvidenceRegistry",
    "GitCollector", "LogCollector", "ConfigCollector", "DepDiffCollector",
    "_REGISTRY",
]
