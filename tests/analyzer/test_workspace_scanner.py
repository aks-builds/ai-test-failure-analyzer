# tests/analyzer/test_workspace_scanner.py
from __future__ import annotations
from pathlib import Path
import json
import pytest
from analyzer.workspace_scanner import scan_workspace, WorkspaceProfile, NOISE_KEYWORDS


def _dirs(tmp: Path, *names: str) -> Path:
    for n in names:
        (tmp / n).mkdir(parents=True, exist_ok=True)
    return tmp


def _file(tmp: Path, rel: str, content: str = "{}") -> Path:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_full_source_via_src(tmp_path):
    _dirs(tmp_path, "src", "tests")
    p = scan_workspace(tmp_path)
    assert p.mode == "FULL_SOURCE"
    assert any(d.name == "src" for d in p.source_roots)


def test_full_source_via_api(tmp_path):
    _dirs(tmp_path, "api")
    assert scan_workspace(tmp_path).mode == "FULL_SOURCE"


def test_full_source_via_lib(tmp_path):
    _dirs(tmp_path, "lib")
    assert scan_workspace(tmp_path).mode == "FULL_SOURCE"


def test_full_source_via_app(tmp_path):
    _dirs(tmp_path, "app")
    assert scan_workspace(tmp_path).mode == "FULL_SOURCE"


def test_api_only_when_no_source_dirs(tmp_path):
    _dirs(tmp_path, "tests")
    assert scan_workspace(tmp_path).mode == "API_ONLY"


def test_api_only_empty_workspace(tmp_path):
    assert scan_workspace(tmp_path).mode == "API_ONLY"


def test_force_api_only_overrides_src(tmp_path):
    _dirs(tmp_path, "src")
    p = scan_workspace(tmp_path, force_api_only=True)
    assert p.mode == "API_ONLY"


def test_test_roots_detected(tmp_path):
    _dirs(tmp_path, "src", "tests", "e2e")
    p = scan_workspace(tmp_path)
    names = {d.name for d in p.test_roots}
    assert "tests" in names
    assert "e2e" in names


def test_noise_paths_fixtures_and_mocks(tmp_path):
    _dirs(tmp_path, "src", "tests/fixtures", "tests/__mocks__")
    p = scan_workspace(tmp_path)
    noise_names = {d.name for d in p.noise_paths}
    assert "fixtures" in noise_names
    assert "__mocks__" in noise_names


def test_has_git(tmp_path):
    _dirs(tmp_path, "src", ".git")
    assert scan_workspace(tmp_path).has_git is True


def test_no_git(tmp_path):
    _dirs(tmp_path, "src")
    assert scan_workspace(tmp_path).has_git is False


def test_openapi_yaml_detected_at_root(tmp_path):
    _dirs(tmp_path, "src")
    _file(tmp_path, "openapi.yaml", '{"openapi":"3.0"}')
    p = scan_workspace(tmp_path)
    assert p.openapi_spec is not None
    assert p.openapi_spec.name == "openapi.yaml"


def test_swagger_json_detected_at_root(tmp_path):
    _dirs(tmp_path, "src")
    _file(tmp_path, "swagger.json", '{"swagger":"2.0"}')
    p = scan_workspace(tmp_path)
    assert p.openapi_spec is not None


def test_no_openapi_spec(tmp_path):
    _dirs(tmp_path, "src")
    assert scan_workspace(tmp_path).openapi_spec is None


def test_default_noise_keywords_present(tmp_path):
    _dirs(tmp_path, "src")
    p = scan_workspace(tmp_path)
    assert "intentional" in p.noise_keywords
    assert "deliberately" in p.noise_keywords


def test_custom_noise_keywords_merged(tmp_path):
    _dirs(tmp_path, "src", ".atfa")
    _file(tmp_path, ".atfa/noise-keywords.json",
          json.dumps(["custom-skip", "internal-demo"]))
    p = scan_workspace(tmp_path)
    assert "custom-skip" in p.noise_keywords
    assert "internal-demo" in p.noise_keywords
    assert "intentional" in p.noise_keywords  # defaults still present


def test_malformed_custom_keywords_ignored(tmp_path):
    _dirs(tmp_path, "src", ".atfa")
    _file(tmp_path, ".atfa/noise-keywords.json", "not-json{{")
    p = scan_workspace(tmp_path)  # must not raise
    assert "intentional" in p.noise_keywords
