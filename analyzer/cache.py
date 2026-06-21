"""Analysis result caching — SHA1 key, 24h expiry, .atfa/cache/ storage."""
from __future__ import annotations
import dataclasses
import hashlib
import json
import os
import time
from pathlib import Path

_CACHE_DIR = ".atfa/cache"
_EXPIRY_SECONDS = 86400  # 24 hours


class CacheKey:
    @staticmethod
    def compute(workspace: Path, results_path: Path) -> str:
        """SHA1 of: git HEAD (if exists) + results file mtime + results file size + SHA1 of file contents."""
        parts: list[str] = []
        git_head = workspace / ".git" / "HEAD"
        if git_head.exists():
            try:
                ref = git_head.read_text().strip()
                # Resolve symbolic ref
                if ref.startswith("ref:"):
                    ref_path = workspace / ".git" / ref[5:].strip()
                    if ref_path.exists():
                        ref = ref_path.read_text().strip()
                parts.append(ref)
            except OSError:
                pass
        try:
            stat = results_path.stat()
            parts.append(f"{stat.st_mtime_ns}:{stat.st_size}")
            # Include a content hash so changes within the same mtime tick are detected
            content = results_path.read_bytes()
            parts.append(hashlib.sha1(content).hexdigest())
        except OSError:
            parts.append(str(results_path))
        seed = ":".join(parts)
        return hashlib.sha1(seed.encode()).hexdigest()


def _cache_path(workspace: Path, key: str) -> Path:
    return workspace / _CACHE_DIR / f"{key}.json"


def load_cached(workspace: Path, key: str):
    """Return cached AnalysisResult or None if missing/expired/invalid."""
    p = _cache_path(workspace, key)
    if not p.exists():
        return None
    try:
        age = time.time() - p.stat().st_mtime
        if age > _EXPIRY_SECONDS:
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        # Reconstruct AnalysisResult from dict (minimal fields only)
        from .orchestrator import AnalysisResult
        from .workspace_scanner import WorkspaceProfile
        from .parsers.base import NormalizedFailure
        profile_data = data.get("profile") or {}
        profile = WorkspaceProfile(
            mode=profile_data.get("mode", "API_ONLY"),
            source_roots=[],
            test_roots=[],
            noise_paths=[],
            openapi_spec=None,
            has_git=profile_data.get("has_git", False),
        )
        _valid_fields = set(NormalizedFailure.__dataclass_fields__)
        failures_data = data.get("failures", [])
        failures = [
            NormalizedFailure(**{k: v for k, v in fd.items() if k in _valid_fields})
            for fd in failures_data
        ]
        return AnalysisResult(
            framework=data["framework"],
            failures=failures,
            git=data.get("git", {}),
            logs=data.get("logs", {}),
            config=data.get("config", {}),
            matrix=data.get("matrix", []),
            clusters=data.get("clusters", []),
            hypotheses=[],  # hypotheses reconstructed from report
            report_markdown=data.get("report_markdown", ""),
            elapsed_seconds=data.get("elapsed_seconds", 0),
            profile=profile,
            suppressed_hypotheses=data.get("suppressed_hypotheses", 0),
            no_app_fault=data.get("no_app_fault", False),
            phase_timings=data.get("phase_timings", {}),
        )
    except Exception:
        return None


def save_cache(workspace: Path, key: str, result) -> None:
    """Persist AnalysisResult to cache. Best-effort — never raises."""
    try:
        p = _cache_path(workspace, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "framework": result.framework,
            "git": result.git,
            "logs": result.logs,
            "config": result.config,
            "matrix": result.matrix,
            "clusters": result.clusters,
            "report_markdown": result.report_markdown,
            "elapsed_seconds": result.elapsed_seconds,
            "suppressed_hypotheses": result.suppressed_hypotheses,
            "no_app_fault": result.no_app_fault,
            "phase_timings": getattr(result, "phase_timings", {}),
            "profile": dataclasses.asdict(result.profile) if result.profile else {},
            "failures": [
                {
                    "id": f.id,
                    "framework": f.framework,
                    "suite": f.suite,
                    "title": f.title,
                    "file": f.file,
                    "line": f.line,
                    "duration_ms": f.duration_ms,
                    "status": f.status,
                    "error_message": f.error_message,
                    "error_stack": f.error_stack,
                    "expected": f.expected,
                    "actual": f.actual,
                    "http": f.http,
                    "attachments": f.attachments,
                    "flakiness_score": f.flakiness_score,
                    "flakiness_category": f.flakiness_category,
                    "ctrf_extra": f.ctrf_extra,
                }
                for f in result.failures
            ],
        }
        p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass
