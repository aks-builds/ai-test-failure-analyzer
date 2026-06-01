"""Security primitive tests — must not regress."""

from __future__ import annotations

import pytest

from analyzer.security import (
    SecurityError,
    cap_raw_record,
    safe_path,
    truncate_bytes,
    validate_commit_hash,
    validate_git_args,
)


def test_safe_path_rejects_traversal(tmp_path):
    with pytest.raises(SecurityError):
        safe_path(tmp_path, "../../etc/passwd")


def test_safe_path_accepts_subpath(tmp_path):
    sub = tmp_path / "a" / "b.txt"
    sub.parent.mkdir(parents=True)
    sub.write_text("x")
    result = safe_path(tmp_path, "a/b.txt")
    assert result == sub.resolve()


def test_validate_git_args_whitelist():
    assert validate_git_args(["log", "--oneline"]) == ["log", "--oneline"]
    with pytest.raises(SecurityError):
        validate_git_args(["push", "--force"])
    with pytest.raises(SecurityError):
        validate_git_args(["log; rm -rf /"])


def test_validate_git_args_rejects_metacharacters():
    with pytest.raises(SecurityError):
        validate_git_args(["log", "foo|bar"])
    with pytest.raises(SecurityError):
        validate_git_args(["log", "x`whoami`"])


def test_validate_commit_hash():
    assert validate_commit_hash("abcdef1") == "abcdef1"
    assert validate_commit_hash("a" * 40) == "a" * 40
    with pytest.raises(SecurityError):
        validate_commit_hash("not-a-hash")
    with pytest.raises(SecurityError):
        validate_commit_hash("abc")  # too short


def test_truncate_bytes():
    assert truncate_bytes("hello", cap=100) == "hello"
    long = "x" * 10_000
    out = truncate_bytes(long, cap=100)
    assert len(out.encode()) <= 100
    assert out.endswith("…[truncated]")


def test_cap_raw_record():
    big = {"k": "x" * 100_000}
    capped = cap_raw_record(big, cap=1024)
    assert capped.get("__truncated__") is True
