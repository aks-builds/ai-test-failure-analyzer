"""Artillery JSON summary parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_http


class ArtilleryJsonParser(Parser):
    """Parses Artillery --output JSON summary files.
    Sniff: 'aggregate' + 'scenariosCreated' top-level keys."""
    framework = "artillery"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"aggregate"' in text and '"scenariosCreated"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        agg = data.get("aggregate", {})
        results: list[NormalizedFailure] = []

        # Each error type becomes a failure
        for error_type, count in (agg.get("errors") or {}).items():
            title = f"Artillery error: {error_type} ({count} occurrences)"
            http = parse_http(title, error_type, None)
            results.append(NormalizedFailure(
                id=make_failure_id("artillery", "aggregate", title, "simulation"),
                framework="artillery",
                suite="aggregate",
                title=title,
                file="simulation",
                status="failed",
                error_message=f"{count} occurrences of {error_type}",
                http=http,
                raw={"error": error_type, "count": count},
            ))

        # HTTP error codes (4xx/5xx) as failures
        for code_str, count in (agg.get("codes") or {}).items():
            try:
                code = int(code_str)
            except ValueError:
                continue
            if code >= 400:
                title = f"HTTP {code} responses ({count} occurrences)"
                http = {"method": None, "url": None, "status_got": code, "status_expected": 200}
                results.append(NormalizedFailure(
                    id=make_failure_id("artillery", "http", title, "simulation"),
                    framework="artillery",
                    suite="http",
                    title=title,
                    file="simulation",
                    status="failed",
                    error_message=f"{count} requests returned HTTP {code}",
                    http=http,
                    raw={"code": code, "count": count},
                ))

        return results
