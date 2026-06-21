"""Optional LLM enrichment — appended to report only when --enrich flag is set.

Uses urllib.request (stdlib) to call any compatible LLM endpoint.
Never required for the deterministic analysis to work.
"""
from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from analyzer.orchestrator import AnalysisResult

_PROMPT_TEMPLATE = """\
You are a software debugging expert. Below is a deterministic test failure analysis \
report produced by ai-test-failure-analyzer. The report already identifies the most \
likely root causes. Your task is to:
1. Confirm or gently correct the top hypothesis in plain language.
2. Suggest a specific code fix (show the file path and the change needed).
3. Mention any related documentation or patterns to watch for.

Be concise — under 300 words. Start your response with "## AI Enrichment".

FRAMEWORK: {framework}
MODE: {mode}
TOP HYPOTHESIS: {hypothesis_json}
"""

_OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
_CLAUDE_ENDPOINT = "https://api.anthropic.com/v1/messages"


@dataclass
class EnrichConfig:
    provider: str   # "claude" | "openai" | "ollama" | "custom"
    endpoint: str
    api_key: str
    model: str

    def __repr__(self) -> str:
        return (
            f"EnrichConfig(provider={self.provider!r}, endpoint={self.endpoint!r}, "
            f"api_key=\"***\", model={self.model!r})"
        )

    @classmethod
    def from_env(cls) -> "EnrichConfig":
        key = os.environ.get("ATFA_LLM_KEY") or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("No LLM API key configured. Set ATFA_LLM_KEY or OPENAI_API_KEY.")
        endpoint = os.environ.get("ATFA_LLM_ENDPOINT", _OPENAI_ENDPOINT)
        model = os.environ.get("ATFA_LLM_MODEL", "gpt-4o")
        if os.environ.get("ATFA_LLM_KEY") and not os.environ.get("ATFA_LLM_ENDPOINT"):
            # Default to Claude if ATFA_LLM_KEY set without custom endpoint
            endpoint = _CLAUDE_ENDPOINT
            model = os.environ.get("ATFA_LLM_MODEL", "claude-sonnet-4-6")
        # ATFA_LLM_PROVIDER overrides auto-detection when explicitly set
        explicit_provider = os.environ.get("ATFA_LLM_PROVIDER", "").lower()
        if explicit_provider:
            provider = explicit_provider
        else:
            endpoint_lower = endpoint.lower()
            if "anthropic" in endpoint_lower:
                provider = "claude"
            elif "openai" in endpoint_lower:
                provider = "openai"
            elif "11434" in endpoint_lower or "ollama" in endpoint_lower:
                provider = "ollama"
            else:
                provider = "custom"
        return cls(provider=provider, endpoint=endpoint, api_key=key, model=model)


def _build_prompt(result: AnalysisResult) -> str:
    top_hyp = result.hypotheses[0].to_dict() if result.hypotheses else {}
    return _PROMPT_TEMPLATE.format(
        framework=result.framework,
        mode=result.profile.mode if result.profile else "unknown",
        hypothesis_json=json.dumps(top_hyp, indent=2)[:800],
    )


def _call_openai(config: EnrichConfig, prompt: str) -> str:
    body = json.dumps({
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
    }).encode()
    req = urllib.request.Request(
        config.endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _call_ollama(config: EnrichConfig, prompt: str) -> str:
    try:
        body = json.dumps({
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            config.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["message"]["content"]
    except Exception:
        return ""


def _call_claude(config: EnrichConfig, prompt: str) -> str:
    body = json.dumps({
        "model": config.model,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        config.endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"]


def enrich(result: AnalysisResult, config: EnrichConfig) -> str:
    """Call configured LLM endpoint and return enrichment markdown.

    Returns empty string on any failure — never raises.
    """
    try:
        prompt = _build_prompt(result)
        if config.provider == "claude":
            return _call_claude(config, prompt)
        elif config.provider == "ollama":
            return _call_ollama(config, prompt)
        else:
            return _call_openai(config, prompt)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError):
        return ""
    except Exception:
        return ""
