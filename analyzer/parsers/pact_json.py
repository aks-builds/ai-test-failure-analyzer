"""Pact contract test results parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class PactJsonParser(Parser):
    """Parses Pact contract verification results JSON.
    Sniff: 'consumer' + 'provider' + 'interactions' keys."""
    framework = "pact"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"consumer"' in text and '"provider"' in text and '"interactions"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        consumer = (data.get("consumer") or {}).get("name", "consumer")
        provider = (data.get("provider") or {}).get("name", "provider")
        suite = f"{consumer} -> {provider}"
        results: list[NormalizedFailure] = []
        for interaction in data.get("interactions", []):
            description = interaction.get("description", "")
            verified = interaction.get("verified", True)
            error_msg = interaction.get("verificationError")
            status = "failed" if not verified else "passed"
            req = interaction.get("request") or {}
            resp = interaction.get("response") or {}
            http = {
                "method": req.get("method"),
                "url": req.get("path"),
                "status_got": None,
                "status_expected": resp.get("status"),
            }
            expected, actual = parse_assertion(error_msg, None)
            results.append(NormalizedFailure(
                id=make_failure_id("pact", suite, description, path.name),
                framework="pact",
                suite=suite,
                title=description,
                file=path.name,
                status=status,
                error_message=error_msg,
                expected=expected,
                actual=actual,
                http=http,
                raw=interaction,
            ))
        return results
