"""Tests for optional LLM enrichment."""
import json
import pytest
from unittest.mock import patch, MagicMock


def _minimal_result():
    from analyzer.orchestrator import AnalysisResult
    from analyzer.workspace_scanner import WorkspaceProfile
    return AnalysisResult(
        framework="playwright", failures=[], git={}, logs={}, config={},
        matrix=[], clusters=[], hypotheses=[],
        report_markdown="# report", elapsed_seconds=1.0,
        profile=WorkspaceProfile(mode="FULL_SOURCE", source_roots=[],
                                  test_roots=[], noise_paths=[],
                                  openapi_spec=None, has_git=False),
        phase_timings={},
    )


def test_enrich_config_no_key_raises():
    from analyzer.enricher import EnrichConfig
    with pytest.raises(ValueError, match="No LLM"):
        EnrichConfig.from_env()  # no env vars set


def test_enrich_config_reads_env(monkeypatch):
    from analyzer.enricher import EnrichConfig
    monkeypatch.setenv("ATFA_LLM_KEY", "test-key")
    monkeypatch.setenv("ATFA_LLM_ENDPOINT", "https://api.example.com/v1/chat")
    config = EnrichConfig.from_env()
    assert config.api_key == "test-key"
    assert "example.com" in config.endpoint


def test_enrich_returns_string_on_success(monkeypatch):
    """enrich() returns a markdown string when the LLM call succeeds."""
    from analyzer.enricher import enrich, EnrichConfig
    result = _minimal_result()
    config = EnrichConfig(
        provider="custom",
        endpoint="https://api.example.com",
        api_key="test-key",
        model="test-model",
    )
    mock_response = json.dumps({
        "choices": [{"message": {"content": "## AI Enrichment\n\nRoot cause confirmed."}}]
    }).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        output = enrich(result, config)
    assert "AI Enrichment" in output or "Root cause" in output


def test_enrich_returns_empty_on_http_error(monkeypatch):
    """enrich() returns empty string (not raises) on HTTP failure."""
    from analyzer.enricher import enrich, EnrichConfig
    import urllib.error
    result = _minimal_result()
    config = EnrichConfig(provider="custom", endpoint="https://bad", api_key="k", model="m")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        output = enrich(result, config)
    assert output == ""
