# analyzer/parsers/k6_json.py
from __future__ import annotations

import json
from pathlib import Path

from .base import NormalizedFailure, Parser, make_failure_id


def _collect_failed_checks(group: dict, suite_name: str, out: list[dict]) -> None:
    """Recursively walk k6 group tree and collect failed checks."""
    for check in group.get("checks") or []:
        fails = check.get("fails", 0)
        if fails > 0:
            total = check.get("passes", 0) + fails
            out.append({
                "name": check.get("name", ""),
                "suite": suite_name or "k6 load test",
                "error_msg": f"{fails}/{total} runs failed",
            })
    groups = group.get("groups") or {}
    for sub in (groups.values() if isinstance(groups, dict) else groups):
        _collect_failed_checks(sub, sub.get("name", suite_name), out)


class K6JsonParser(Parser):
    """Parser for k6 summary JSON (--summary-export / --out json).

    k6 invocation:
        k6 run --summary-export=results.json script.js
    """

    framework = "k6"

    @classmethod
    def can_parse(cls, sample: str | bytes) -> bool:
        if isinstance(sample, bytes):
            try:
                sample = sample.decode("utf-8", errors="replace")
            except Exception:
                return False
        s = sample.lstrip()
        return s.startswith("{") and '"root_group"' in s and '"metrics"' in s

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        metrics = data.get("metrics") or {}
        duration_values = (metrics.get("http_req_duration") or {}).get("values") or {}
        p95_raw = duration_values.get("p(95)") or duration_values.get("p95")
        p95_ms = int(p95_raw) if p95_raw is not None else None

        failed_checks: list[dict] = []
        _collect_failed_checks(data.get("root_group") or {}, "k6 load test", failed_checks)

        return [
            NormalizedFailure(
                id=make_failure_id(cls.framework, c["suite"], c["name"], ""),
                framework=cls.framework,
                suite=c["suite"],
                title=c["name"],
                file="",
                status="failed",
                error_message=c["error_msg"],
                http={
                    "method": None,
                    "url": None,
                    "status_got": None,
                    "status_expected": None,
                    "response_time_ms": p95_ms,
                },
            )
            for c in failed_checks
        ]
