"""OtelCollector — reads OpenTelemetry trace exports for span correlation. Tier-1."""
from __future__ import annotations
import json
import os
import urllib.request
from pathlib import Path

from ..bundle import EvidenceBundle
from ..collector import EvidenceCollector
from ..graph import EvidenceNode

_TRACE_FILES = ["traces.json", "otel-traces.json", "otel_traces.json"]


def _find_trace_file(workspace: Path) -> Path | None:
    for name in _TRACE_FILES:
        p = workspace / name
        if p.exists():
            return p
    # Also check *.otlp.json
    for p in workspace.glob("*.otlp.json"):
        return p
    return None


def _extract_spans(data: dict) -> list[dict]:
    """Extract span dicts from OTLP JSON export format."""
    spans = []
    for resource_span in data.get("resourceSpans", []):
        for scope_span in resource_span.get("scopeSpans", []):
            spans.extend(scope_span.get("spans", []))
    return spans


def _attr_value(attrs: list[dict], key: str):
    for a in attrs:
        if a.get("key") == key:
            v = a.get("value", {})
            return v.get("stringValue") or v.get("intValue") or v.get("boolValue")
    return None


class OtelCollector(EvidenceCollector):
    """Reads OTel trace export files or HTTP endpoint. Tier-1 when available."""
    name = "otel"
    tier = "tier1"

    @classmethod
    def is_available(cls, workspace: Path, profile) -> bool:
        if _find_trace_file(workspace):
            return True
        return bool(os.environ.get("ATFA_OTEL_ENDPOINT"))

    @classmethod
    def collect(cls, workspace: Path, profile) -> EvidenceBundle:
        try:
            return cls._collect_safe(workspace)
        except Exception:
            return EvidenceBundle.empty("otel", "tier1")

    @classmethod
    def _collect_safe(cls, workspace: Path) -> EvidenceBundle:
        data = None
        trace_file = _find_trace_file(workspace)
        if trace_file:
            try:
                data = json.loads(trace_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return EvidenceBundle(
                    collector_name="otel", tier="tier1", available=False,
                    summary={"status": "invalid trace file"},
                    legacy={"available": False, "summary": {"status": "invalid trace file"}},
                )
        elif os.environ.get("ATFA_OTEL_ENDPOINT"):
            endpoint = os.environ["ATFA_OTEL_ENDPOINT"]
            try:
                with urllib.request.urlopen(endpoint, timeout=5) as resp:
                    data = json.loads(resp.read())
            except Exception:
                return EvidenceBundle.empty("otel", "tier1")

        if not data:
            return EvidenceBundle.empty("otel", "tier1")

        spans = _extract_spans(data)
        nodes: list[EvidenceNode] = []
        for i, span in enumerate(spans[:50]):  # cap at 50 spans
            status = span.get("status") or {}
            status_code = status.get("code", 0)  # 2 = ERROR in OTLP
            attrs = span.get("attributes", [])
            http_url = _attr_value(attrs, "http.url") or _attr_value(attrs, "http.target") or ""
            http_status = _attr_value(attrs, "http.status_code")
            is_error = status_code == 2 or (isinstance(http_status, int) and http_status >= 400)
            weight = 2.0 if is_error else 1.0
            excerpt = (
                f"{span.get('name', '')} "
                f"{'status=' + str(http_status) if http_status else ''} "
                f"{'ERROR' if is_error else ''}"
            ).strip()
            nodes.append(EvidenceNode(
                id=f"span:{span.get('spanId', str(i))}",
                type="span",
                ref=http_url or span.get("name", f"span:{i}"),
                weight=weight,
                excerpt=excerpt[:200],
            ))

        return EvidenceBundle(
            collector_name="otel",
            tier="tier1",
            available=bool(nodes),
            nodes=nodes,
            summary={"spans": len(spans), "error_spans": sum(1 for n in nodes if n.weight >= 2.0)},
            legacy={"available": bool(nodes),
                    "spans": [n.ref for n in nodes if n.weight >= 2.0],
                    "summary": {"spans": len(spans)}},
        )
