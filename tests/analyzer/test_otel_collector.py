"""Tests for OtelCollector and FlakyHistoryCollector."""
import json
import pytest
from pathlib import Path


def test_otel_unavailable_when_no_traces(tmp_path):
    from analyzer.evidence.collectors.otel_collector import OtelCollector
    import os
    env_backup = os.environ.pop("ATFA_OTEL_ENDPOINT", None)
    try:
        assert OtelCollector.is_available(tmp_path, profile=None) is False
    finally:
        if env_backup:
            os.environ["ATFA_OTEL_ENDPOINT"] = env_backup


def test_otel_available_when_trace_file_exists(tmp_path):
    from analyzer.evidence.collectors.otel_collector import OtelCollector
    (tmp_path / "traces.json").write_text('{"resourceSpans": []}')
    assert OtelCollector.is_available(tmp_path, profile=None) is True


def test_otel_collect_parses_spans(tmp_path):
    from analyzer.evidence.collectors.otel_collector import OtelCollector
    spans = {
        "resourceSpans": [{
            "scopeSpans": [{
                "spans": [{
                    "name": "POST /api/users",
                    "status": {"code": 2, "message": "Error"},
                    "attributes": [
                        {"key": "http.url", "value": {"stringValue": "/api/users"}},
                        {"key": "http.status_code", "value": {"intValue": 500}}
                    ]
                }]
            }]
        }]
    }
    (tmp_path / "traces.json").write_text(json.dumps(spans))
    bundle = OtelCollector.collect(tmp_path, profile=None)
    assert bundle.available is True
    assert len(bundle.nodes) >= 1


def test_otel_collect_never_raises_on_invalid_file(tmp_path):
    from analyzer.evidence.collectors.otel_collector import OtelCollector
    (tmp_path / "traces.json").write_text("not valid json {{{")
    bundle = OtelCollector.collect(tmp_path, profile=None)
    assert bundle is not None


def test_flaky_history_unavailable_when_no_file(tmp_path):
    from analyzer.evidence.collectors.flaky_history_collector import FlakyHistoryCollector
    assert FlakyHistoryCollector.is_available(tmp_path, profile=None) is False


def test_flaky_history_available_when_file_exists(tmp_path):
    from analyzer.evidence.collectors.flaky_history_collector import FlakyHistoryCollector
    atfa = tmp_path / ".atfa"
    atfa.mkdir()
    (atfa / "history.json").write_text('{"runs": []}')
    assert FlakyHistoryCollector.is_available(tmp_path, profile=None) is True


def test_flaky_history_collect_returns_bundle(tmp_path):
    from analyzer.evidence.collectors.flaky_history_collector import FlakyHistoryCollector
    atfa = tmp_path / ".atfa"
    atfa.mkdir()
    history = {
        "runs": [
            {"run_id": "r1", "failures": [{"id": "abc", "status": "failed"}]},
            {"run_id": "r2", "failures": []},
        ]
    }
    (atfa / "history.json").write_text(json.dumps(history))
    bundle = FlakyHistoryCollector.collect(tmp_path, profile=None)
    assert bundle.available is True
    assert "history" in bundle.legacy
