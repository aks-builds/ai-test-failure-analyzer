"""FastAPI + HTMX web dashboard for the analyzer.

Loopback only by default. Routes:
- GET  /           dashboard shell
- POST /analyze    HTMX form-post → triggers analysis, returns HTML fragment with hypotheses
- POST /issue      HTMX form-post → creates GitHub issue (dry-run if no token)
- GET  /report.md  download the last analysis as Markdown
"""

from __future__ import annotations

import logging
import threading
import webbrowser
from html import escape
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ...config import github_repository, github_token
from ...github_integration import create_issue_from_hypothesis, detect_default_repo
from ...orchestrator import AnalysisResult, analyze
from ...render.markdown import render_markdown_report

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))

app = FastAPI(title="QA Test Failure Analyzer", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

# In-process cache of the most recent result (so /issue and /report.md can reuse it)
_last_result: dict[str, Any] = {"result": None}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "default_results_path": "test-results/results.json",
            "default_repo": detect_default_repo() or "",
            "has_token": bool(github_token()),
        },
    )


@app.post("/analyze", response_class=HTMLResponse)
async def do_analyze(
    request: Request,
    results_path: str = Form("test-results/results.json"),
    framework: str = Form("auto"),
) -> HTMLResponse:
    try:
        result = analyze(
            results_path=results_path,
            framework=framework,
            ask=None,
            progress=None,
        )
    except FileNotFoundError:
        return HTMLResponse(
            "<div class='alert error'>&#x2717; Test results file not found. Check the path and try again.</div>",
            status_code=200,
        )
    except Exception:
        _log.exception("Analysis failed for request from web UI")
        return HTMLResponse(
            "<div class='alert error'>&#x2717; Analysis failed. Check server logs for details.</div>",
            status_code=200,
        )

    _last_result["result"] = result
    return templates.TemplateResponse(
        request,
        "_report.html",
        {
            "result": result,
            "failures_failed": [f for f in result.failures if f.status == "failed"],
            "default_repo": detect_default_repo() or github_repository() or "",
            "has_token": bool(github_token()),
        },
    )


@app.post("/issue", response_class=HTMLResponse)
async def do_issue(
    request: Request,
    repo: str = Form(...),
    cluster_id: str = Form(...),
    live: str = Form("0"),
) -> HTMLResponse:
    try:
        result: AnalysisResult | None = _last_result.get("result")
        if not result or not result.hypotheses:
            return HTMLResponse("<div class='alert error'>No analysis result in memory. Run analysis first.</div>")

        hyp = next((h for h in result.hypotheses if h.cluster_id == cluster_id), result.hypotheses[0])
        is_dry = live != "1" or not github_token()
        out = create_issue_from_hypothesis(repo=repo, hypothesis=hyp, dry_run=is_dry)

        if out.get("created"):
            safe_url = escape(str(out.get("url", "")))
            return HTMLResponse(
                f"<div class='alert success'>&#x2713; Issue created: "
                f"<a href='{safe_url}' target='_blank' rel='noopener noreferrer'>{safe_url}</a></div>"
            )
        if out.get("dry_run"):
            wc = out.get("would_create") or {}
            body_bytes = int(wc.get("body_bytes") or 0)
            return HTMLResponse(
                f"<div class='alert info'>Dry-run preview:<br>"
                f"<b>Repo:</b> {escape(str(wc.get('repo', '')))}<br>"
                f"<b>Title:</b> {escape(str(wc.get('title', '')))}<br>"
                f"<b>Labels:</b> {escape(', '.join(str(l) for l in wc.get('labels', [])))}<br>"
                f"<b>Body:</b> {body_bytes} bytes</div>"
            )
        _log.warning("Issue creation failed: %s", out.get("reason", "unknown"))
        return HTMLResponse("<div class='alert error'>&#x2717; Could not create issue. Check server logs.</div>")
    except Exception:
        _log.exception("Unhandled error in /issue endpoint")
        return HTMLResponse("<div class='alert error'>&#x2717; Operation failed. Check server logs.</div>")


@app.get("/report.md", response_class=PlainTextResponse)
async def download_md() -> PlainTextResponse:
    result: AnalysisResult | None = _last_result.get("result")
    if not result:
        raise HTTPException(status_code=404, detail="no analysis yet")
    return PlainTextResponse(result.report_markdown, media_type="text/markdown")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "has_last_result": _last_result.get("result") is not None}


def run(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    import uvicorn

    if open_browser:
        def _open() -> None:
            import time as _t
            _t.sleep(0.8)
            webbrowser.open(f"http://{host}:{port}/")

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
