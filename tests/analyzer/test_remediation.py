"""Tests for analyzer.remediation — language-specific remediation module."""
from __future__ import annotations

import pytest


def test_language_for_framework_known_js_frameworks():
    from analyzer.remediation import language_for_framework
    assert language_for_framework("playwright") == "js"
    assert language_for_framework("cypress") == "js"
    assert language_for_framework("jest") == "js"
    assert language_for_framework("vitest") == "js"
    assert language_for_framework("mocha") == "js"
    assert language_for_framework("wdio") == "js"
    assert language_for_framework("detox") == "js"


def test_language_for_framework_known_python_frameworks():
    from analyzer.remediation import language_for_framework
    assert language_for_framework("pytest") == "python"
    assert language_for_framework("robot") == "python"


def test_language_for_framework_known_go():
    from analyzer.remediation import language_for_framework
    assert language_for_framework("go") == "go"


def test_language_for_framework_known_jvm():
    from analyzer.remediation import language_for_framework
    assert language_for_framework("junit") == "jvm"
    assert language_for_framework("rest-assured") == "jvm"
    assert language_for_framework("karate") == "jvm"
    assert language_for_framework("testng") == "jvm"


def test_language_for_framework_known_dotnet():
    from analyzer.remediation import language_for_framework
    assert language_for_framework("nunit") == "dotnet"
    assert language_for_framework("xunit") == "dotnet"
    assert language_for_framework("mstest") == "dotnet"


def test_language_for_framework_known_ruby_php():
    from analyzer.remediation import language_for_framework
    assert language_for_framework("rspec") == "ruby"
    assert language_for_framework("phpunit") == "php"


def test_language_for_framework_known_load():
    from analyzer.remediation import language_for_framework
    assert language_for_framework("k6") == "load"
    assert language_for_framework("artillery") == "load"
    assert language_for_framework("gatling") == "load"


def test_language_for_framework_known_api():
    from analyzer.remediation import language_for_framework
    assert language_for_framework("newman") == "api"
    assert language_for_framework("pact") == "api"


def test_language_for_framework_case_insensitive():
    from analyzer.remediation import language_for_framework
    assert language_for_framework("PLAYWRIGHT") == "js"
    assert language_for_framework("PyTest") == "python"


def test_language_for_framework_unknown_returns_unknown():
    from analyzer.remediation import language_for_framework
    assert language_for_framework("nonexistent_framework") == "unknown"
    assert language_for_framework("") == "unknown"


def test_run_command_for_framework_known():
    from analyzer.remediation import run_command_for_framework
    cmd = run_command_for_framework("playwright")
    assert cmd is not None
    assert "playwright" in cmd.lower()


def test_run_command_for_framework_pytest():
    from analyzer.remediation import run_command_for_framework
    cmd = run_command_for_framework("pytest")
    assert cmd is not None
    assert "pytest" in cmd


def test_run_command_for_framework_unknown_returns_none():
    from analyzer.remediation import run_command_for_framework
    assert run_command_for_framework("nonexistent") is None
    assert run_command_for_framework("") is None


def test_run_command_for_framework_case_insensitive():
    from analyzer.remediation import run_command_for_framework
    assert run_command_for_framework("JEST") == run_command_for_framework("jest")


def test_install_prefix_for_language_js():
    from analyzer.remediation import install_prefix_for_language
    prefix = install_prefix_for_language("js")
    assert "npm" in prefix or "npx" in prefix


def test_install_prefix_for_language_python():
    from analyzer.remediation import install_prefix_for_language
    prefix = install_prefix_for_language("python")
    assert "pip" in prefix or "pytest" in prefix


def test_install_prefix_for_language_dotnet():
    from analyzer.remediation import install_prefix_for_language
    prefix = install_prefix_for_language("dotnet")
    assert "dotnet" in prefix


def test_install_prefix_for_language_unknown_returns_fallback():
    from analyzer.remediation import install_prefix_for_language
    prefix = install_prefix_for_language("unknown_lang")
    assert isinstance(prefix, str)
    assert len(prefix) > 0
