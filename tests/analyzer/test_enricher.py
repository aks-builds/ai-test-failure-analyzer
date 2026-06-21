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


def test_enrich_config_no_key_raises(monkeypatch):
    from analyzer.enricher import EnrichConfig
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ATFA_LLM_KEY", raising=False)
    monkeypatch.delenv("ATFA_LLM_PROVIDER", raising=False)
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


def test_enrich_config_ollama_auto_detect_port(monkeypatch):
    """Auto-detects Ollama by port 11434 in endpoint."""
    from analyzer.enricher import EnrichConfig
    monkeypatch.setenv("ATFA_LLM_KEY", "ignored")
    monkeypatch.setenv("ATFA_LLM_ENDPOINT", "http://localhost:11434/api/chat")
    monkeypatch.delenv("ATFA_LLM_PROVIDER", raising=False)
    config = EnrichConfig.from_env()
    assert config.provider == "ollama"


def test_enrich_config_ollama_auto_detect_name(monkeypatch):
    """Auto-detects Ollama by 'ollama' in endpoint hostname."""
    from analyzer.enricher import EnrichConfig
    monkeypatch.setenv("ATFA_LLM_KEY", "ignored")
    monkeypatch.setenv("ATFA_LLM_ENDPOINT", "http://ollama.internal/api/chat")
    monkeypatch.delenv("ATFA_LLM_PROVIDER", raising=False)
    config = EnrichConfig.from_env()
    assert config.provider == "ollama"


def test_enrich_config_atfa_llm_provider_overrides(monkeypatch):
    """ATFA_LLM_PROVIDER env var overrides auto-detection."""
    from analyzer.enricher import EnrichConfig
    monkeypatch.setenv("ATFA_LLM_KEY", "test-key")
    monkeypatch.setenv("ATFA_LLM_ENDPOINT", "https://api.openai.com/v1/chat/completions")
    monkeypatch.setenv("ATFA_LLM_PROVIDER", "ollama")
    config = EnrichConfig.from_env()
    assert config.provider == "ollama"


def test_enrich_config_repr_masks_key():
    """__repr__ must not expose the actual api_key value."""
    from analyzer.enricher import EnrichConfig
    config = EnrichConfig(
        provider="openai",
        endpoint="https://api.openai.com/v1/chat/completions",
        api_key="sk-supersecret",
        model="gpt-4o",
    )
    r = repr(config)
    assert "sk-supersecret" not in r
    assert "***" in r


def test_enrich_ollama_routing(monkeypatch):
    """enrich() uses Ollama response format when provider='ollama'."""
    from analyzer.enricher import enrich, EnrichConfig
    result = _minimal_result()
    config = EnrichConfig(
        provider="ollama",
        endpoint="http://localhost:11434/api/chat",
        api_key="",
        model="llama3",
    )
    mock_response = json.dumps({
        "message": {"content": "## AI Enrichment\n\nOllama says: root cause confirmed."}
    }).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        output = enrich(result, config)
    assert "Ollama says" in output


def test_enrich_ollama_returns_empty_on_error(monkeypatch):
    """_call_ollama swallows exceptions and returns empty string."""
    from analyzer.enricher import enrich, EnrichConfig
    result = _minimal_result()
    config = EnrichConfig(
        provider="ollama",
        endpoint="http://localhost:11434/api/chat",
        api_key="",
        model="llama3",
    )
    with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("refused")):
        output = enrich(result, config)
    assert output == ""
