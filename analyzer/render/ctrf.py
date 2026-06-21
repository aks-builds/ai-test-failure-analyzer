"""CTRF (Common Test Results Format) output renderer.

Spec: https://github.com/ctrf-io/ctrf — pre-1.0, pinned to schema as of 2026-01.
The 'ai' string field (§9.11) contains a one-line hypothesis summary per test.
"""
from __future__ import annotations
import json
import time
from analyzer.orchestrator import AnalysisResult
from analyzer.hypothesis import Hypothesis

_TOOL_NAME = "ai-test-failure-analyzer"

_CTRF_STATUS_MAP = {"flaky": "other", "error": "failed"}


def _get_tool_version() -> str:
    try:
        from .. import __version__
        return __version__
    except Exception:
        return "2.0.0"


def _find_hypothesis_for_test(title: str, hypotheses: list[Hypothesis]) -> Hypothesis | None:
    for h in hypotheses:
        if title in h.affected_tests:
            return h
    return None


def render_ctrf_report(result: AnalysisResult) -> str:
    """Render analysis result as CTRF JSON string."""
    now_ms = int(time.time() * 1000)
    elapsed_ms = int(result.elapsed_seconds * 1000)

    failures = result.failures
    passed = sum(1 for f in failures if f.status == "passed")
    failed = sum(1 for f in failures if f.status == "failed")
    skipped = sum(1 for f in failures if f.status == "skipped")
    other = sum(
        1 for f in failures
        if _CTRF_STATUS_MAP.get(f.status, f.status) not in ("passed", "failed", "skipped")
    )

    tests_out = []
    for f in failures:
        hyp = _find_hypothesis_for_test(f.title, result.hypotheses)
        ai_str = None
        if hyp:
            ai_str = (
                f"Root cause [{hyp.confidence}%]: {hyp.title}. "
                f"{hyp.summary[:120]} "
                f"Evidence: {'+'.join(sorted({e.source for e in hyp.evidence_chain})) or 'none'}."
            )
        ctrf_status = _CTRF_STATUS_MAP.get(f.status, f.status)
        test_obj: dict = {
            "name": f.title,
            "status": ctrf_status,
            "duration": f.duration_ms or 0,
        }
        if ctrf_status == "failed":
            if f.error_message:
                test_obj["message"] = f.error_message[:500]
            if f.error_stack:
                test_obj["trace"] = f.error_stack[:1000]
        if f.status == "flaky" or (f.flakiness_score or 0) >= 0.5:
            test_obj["flaky"] = True
        if f.file and f.file != "unknown":
            test_obj["filePath"] = f.file
        if f.suite:
            test_obj["suite"] = f.suite
        if ai_str:
            test_obj["ai"] = ai_str[:500]
        # CTRF extra block — computed fields win over raw ctrf_extra
        extra: dict = dict(f.ctrf_extra) if f.ctrf_extra else {}
        if hyp:
            extra["hypothesis_confidence"] = hyp.confidence
            extra["hypothesis_title"] = hyp.title
            if hyp.buggy_location:
                extra["buggy_location"] = hyp.buggy_location
            extra["evidence_sources"] = sorted({e.source for e in hyp.evidence_chain})
        if f.flakiness_score is not None:
            extra["flakiness_score"] = round(f.flakiness_score, 3)
        if f.flakiness_category:
            extra["flakiness_category"] = f.flakiness_category
        if extra:
            test_obj["extra"] = extra
        tests_out.append(test_obj)

    ctrf = {
        "results": {
            "tool": {"name": _TOOL_NAME, "version": _get_tool_version()},
            "summary": {
                "tests": len(failures),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "other": other,
                "start": now_ms - elapsed_ms,
                "stop": now_ms,
            },
            "tests": tests_out,
        }
    }
    return json.dumps(ctrf, indent=2, ensure_ascii=False)
