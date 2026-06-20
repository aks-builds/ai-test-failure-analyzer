"""Gatling simulation.log TSV parser."""
from __future__ import annotations
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_http


class GatlingLogParser(Parser):
    """Parses Gatling simulation.log (TSV format).
    Sniff: first line starts with 'RUN\\t'."""
    framework = "gatling"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        first = sample.split(b"\n")[0].strip()
        return first.startswith(b"RUN\t")

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        results: list[NormalizedFailure] = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("RUN") or line.startswith("END"):
                    continue
                parts = line.split("\t")
                if not parts or parts[0] != "REQUEST":
                    continue
                # Format: REQUEST <user> <start_ms> <end_ms> <request_name> <status> [<message>]
                if len(parts) < 6:
                    continue
                request_name = parts[4] if len(parts) > 4 else "unknown"
                status_str = parts[5] if len(parts) > 5 else "OK"
                message = parts[6] if len(parts) > 6 else None
                status = "failed" if status_str == "KO" else "passed"
                http = parse_http(request_name, message, None)
                results.append(NormalizedFailure(
                    id=make_failure_id("gatling", "simulation", request_name, "simulation.log"),
                    framework="gatling",
                    suite="simulation",
                    title=request_name,
                    file="simulation.log",
                    status=status,
                    error_message=message,
                    http=http,
                    raw={"parts": parts},
                ))
        return results
