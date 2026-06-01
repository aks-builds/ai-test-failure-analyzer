"""Evidence collectors: read git history, scan logs, scan config files, correlate."""

from .config_scan import scan_config
from .correlator import correlate, cluster_failures
from .git_scan import scan_git_history
from .log_scan import scan_logs

__all__ = ["scan_config", "scan_git_history", "scan_logs", "correlate", "cluster_failures"]
