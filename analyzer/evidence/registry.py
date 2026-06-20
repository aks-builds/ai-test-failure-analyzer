"""EvidenceRegistry — discovers and runs all registered collectors."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

from .bundle import EvidenceBundle
from .collector import EvidenceCollector


class EvidenceRegistry:
    """Registry of all EvidenceCollectors. Runs available ones concurrently."""

    def __init__(self) -> None:
        self._collectors: list[type[EvidenceCollector]] = []

    def register(self, collector: type[EvidenceCollector]) -> None:
        """Add a collector class to the registry."""
        self._collectors.append(collector)

    def collect_all(
        self,
        workspace: Path,
        profile,
        timeout: int = 30,
        emit=None,
    ) -> dict[str, EvidenceBundle]:
        """Run all available collectors concurrently.

        Args:
            workspace: Repo root path.
            profile: WorkspaceProfile (may be None in tests).
            timeout: Per-collector timeout in seconds.
            emit: Optional progress callback — called with phase progress dicts.

        Returns:
            Mapping of collector_name → EvidenceBundle.
            Unavailable or failed collectors return EvidenceBundle.empty().
        """
        results: dict[str, EvidenceBundle] = {}
        available = [c for c in self._collectors if c.is_available(workspace, profile)]
        unavailable = [c for c in self._collectors if not c.is_available(workspace, profile)]

        for c in unavailable:
            results[c.name] = EvidenceBundle.empty(c.name, c.tier)
            if emit:
                emit({"collector": c.name, "status": "skipped"})

        if not available:
            return results

        with ThreadPoolExecutor(max_workers=min(len(available), 6)) as pool:
            futures = {pool.submit(c.collect, workspace, profile): c for c in available}
            for future, collector in futures.items():
                try:
                    results[collector.name] = future.result(timeout=timeout)
                    if emit:
                        emit({"collector": collector.name, "status": "completed"})
                except FutureTimeout:
                    results[collector.name] = EvidenceBundle.empty(collector.name, collector.tier)
                    if emit:
                        emit({"collector": collector.name, "status": "timeout"})
                except Exception as exc:
                    results[collector.name] = EvidenceBundle.empty(collector.name, collector.tier)
                    if emit:
                        emit({"collector": collector.name, "status": "error", "error": str(exc)})

        return results
