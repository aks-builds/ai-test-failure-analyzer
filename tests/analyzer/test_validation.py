"""CLI input validation tests — verify clean error messages + exit code 2."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = "tests/analyzer/fixtures/playwright_results.json"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "analyzer", "analyze", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def combined(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


# ── 1. Invalid --format ───────────────────────────────────────────────────────

def test_invalid_format():
    r = run_cli("--results", FIXTURE, "--format", "xml", "--non-interactive")
    assert r.returncode == 2
    assert "Invalid --format" in combined(r)
    assert "Traceback" not in r.stderr


# ── 2. Invalid --mode ─────────────────────────────────────────────────────────

def test_invalid_mode():
    r = run_cli("--results", FIXTURE, "--mode", "cloud", "--non-interactive")
    assert r.returncode == 2
    assert "Invalid --mode" in combined(r)
    assert "Traceback" not in r.stderr


# ── 3. Invalid --workspace (non-existent path) ────────────────────────────────

def test_invalid_workspace():
    r = run_cli(
        "--results", FIXTURE,
        "--workspace", "/no/such/directory/exists",
        "--non-interactive",
    )
    assert r.returncode == 2
    assert "Workspace directory not found" in combined(r)
    assert "Traceback" not in r.stderr


# ── 4. Invalid --out (parent directory missing) ───────────────────────────────

def test_invalid_out_parent():
    r = run_cli(
        "--results", FIXTURE,
        "--out", "/no/such/dir/report.md",
        "--non-interactive",
    )
    assert r.returncode == 2
    assert "Output directory does not exist" in combined(r)
    assert "Traceback" not in r.stderr


# ── 5. Invalid --repo format (no slash) ───────────────────────────────────────

def test_invalid_repo_no_slash():
    r = run_cli(
        "--results", FIXTURE,
        "--repo", "justreponame",
        "--non-interactive",
    )
    assert r.returncode == 2
    assert "Invalid --repo format" in combined(r)
    assert "Traceback" not in r.stderr


# ── 6. Invalid --repo format (too many slashes) ───────────────────────────────

def test_invalid_repo_too_many_slashes():
    r = run_cli(
        "--results", FIXTURE,
        "--repo", "org/repo/extra",
        "--non-interactive",
    )
    assert r.returncode == 2
    assert "Invalid --repo format" in combined(r)
    assert "Traceback" not in r.stderr


# ── 7. Invalid --framework ────────────────────────────────────────────────────

def test_invalid_framework():
    r = run_cli(
        "--results", FIXTURE,
        "--framework", "mytest",
        "--non-interactive",
    )
    assert r.returncode == 2
    assert "Unknown" in combined(r) and "framework" in combined(r).lower()
    assert "Traceback" not in r.stderr
