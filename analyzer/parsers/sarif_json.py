"""SARIF 2.1 (CodeQL, Semgrep, Snyk) results parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id


class SARIFJsonParser(Parser):
    """Parses SARIF 2.1 output from CodeQL, Semgrep, Snyk, etc.
    Sniff: '$schema' containing 'sarif' + 'runs' array."""
    framework = "sarif"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "sarif" in text and '"runs"' in text and '"$schema"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for run in data.get("runs", []):
            tool = (run.get("tool") or {}).get("driver") or {}
            tool_name = tool.get("name", "sarif")
            for result in run.get("results", []):
                level = result.get("level", "warning")
                status = "failed" if level in ("error", "warning") else "passed"
                rule_id = result.get("ruleId", "unknown")
                msg = (result.get("message") or {}).get("text", "")
                title = f"{rule_id}: {msg}" if msg else rule_id
                locations = result.get("locations") or []
                file_path = "unknown"
                line = None
                if locations:
                    phys = (locations[0].get("physicalLocation") or {})
                    art = (phys.get("artifactLocation") or {})
                    file_path = art.get("uri", "unknown")
                    region = phys.get("region") or {}
                    line = region.get("startLine")
                results.append(NormalizedFailure(
                    id=make_failure_id("sarif", tool_name, title, file_path),
                    framework="sarif",
                    suite=tool_name,
                    title=title,
                    file=file_path,
                    line=line,
                    status=status,
                    error_message=msg or None,
                    raw=result,
                ))
        return results
