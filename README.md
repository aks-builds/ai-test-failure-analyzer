# AI Test Failure Analyzer

> An **MCP (Model Context Protocol) server** that performs AI-assisted root-cause analysis on failed test runs.
> Works with **Playwright, pytest, Jest/Vitest, Cypress, and WebdriverIO**. Callable from any MCP-capable AI
> client (Claude Code, Cursor, OpenAI, Gemini), as a CLI, as a TUI, as a local web dashboard, and from CI.

---

## How this repo fits in the demo

```
┌──────────────────────────────────────────────────────┐
│           playwright-userauth-api-suite              │  ← THE TEST REPO
│     github.com/aks-builds/playwright-userauth-api-suite
│                                                      │
│  Playwright tests run → 3 failures detected          │
│  CI installs this package:                           │
│    pip install git+https://github.com/               │
│      aks-builds/ai-test-failure-analyzer.git         │
│  Then calls: analyzer analyze --create-issue         │
│                        │                             │
└────────────────────────│─────────────────────────────┘
                         │
          ┌──────────────▼───────────────────────────────┐
          │         ai-test-failure-analyzer             │  ← YOU ARE HERE
          │   github.com/aks-builds/ai-test-failure-analyzer
          │                                              │
          │  Phase 1  collect_failures  — parse results  │
          │  Phase 2  read_test_intent  — read spec      │
          │  Phase 3  scan_git_history  — flag commits   │
          │  Phase 4  scan_logs         — find errors    │
          │  Phase 5  scan_config       — read env/docs  │
          │  Phase 6  correlate         — cluster causes │
          │  Phase 7  form_hypotheses   — rank + score   │
          │  Phase 8  render_report     — Markdown out   │
          │                                              │
          │  → Creates GitHub Issue in the test repo     │
          └──────────────────────────────────────────────┘
```

---

## What problem does this solve?

The single most time-consuming part of running a test suite at scale is **understanding why something failed**.
Engineers spend 30–60 minutes per regression triaging logs, git history, deployment notes, and Slack threads —
often only to discover the cause was a renamed endpoint or a stale fixture.

This project **automates that triage**:

1. Parses the test report (Playwright JSON, pytest JUnit XML, Jest JSON, Cypress JSON, …)
2. Reads recent git history with risk-pattern flagging
3. Scans application logs for `ERROR`/`FATAL` lines
4. Reads environment / config / changelog files
5. **Cross-correlates** all evidence into failure clusters
6. Produces **ranked root-cause hypotheses** with confidence scores and concrete fix steps
7. Optionally **creates a GitHub issue** with the top hypothesis

All in seconds. With a traceable evidence chain for every claim.

---

## Quick start

```bash
pip install git+https://github.com/aks-builds/ai-test-failure-analyzer.git

# analyze a test results file
analyzer analyze --results path/to/test-results/results.json

# or run as an MCP server for Claude Code / Cursor
analyzer serve-stdio
```

To run the full NashLearn demo (Playwright tests → analysis in one shot), use the companion repo:
[`playwright-userauth-api-suite`](https://github.com/aks-builds/playwright-userauth-api-suite)

---

## Installation (development)

```bash
git clone https://github.com/aks-builds/ai-test-failure-analyzer.git
cd ai-test-failure-analyzer
pip install -e .
```

---

## The five ways to use it

| Mode | Command | Best for |
|---|---|---|
| **CLI** | `analyzer analyze --results results.json` | Local triage, CI scripts |
| **TUI** | `analyzer tui` | Polished terminal UI for screen-share |
| **Web** | `analyzer web` | Browser dashboard at `http://127.0.0.1:8765` |
| **MCP (stdio)** | `analyzer serve-stdio` | Claude Code, Cursor, any local MCP client |
| **MCP (HTTP)** | `analyzer serve-http --port 8765` | OpenAI, Gemini, remote AI clients |

---

## Using it from Claude Code / Cursor

Add to your MCP config:

```jsonc
{
  "mcpServers": {
    "qa-analyzer": {
      "command": "analyzer",
      "args": ["serve-stdio"]
    }
  }
}
```

Then in chat: *"Analyse the failing tests in this repo."*
Claude will call `analyze` (or step through the phase tools individually).

## Using it from any HTTP MCP client

```bash
analyzer serve-http --host 127.0.0.1 --port 8765
```

For non-loopback access, set `ANALYZER_HTTP_TOKEN` — clients must send `Authorization: Bearer <token>`.
The server speaks the standard MCP streamable-HTTP transport at `http://127.0.0.1:8765/mcp`.

---

## MCP tools exposed

Every tool returns a dict with an `evidence` field so the AI can trace its reasoning.

| Tool | Phase | What it does |
|---|---|---|
| `collect_failures` | 1 | Parse the test report into normalized failures |
| `read_test_intent` | 2 | Read a spec file and extract comments + intent around a line |
| `scan_git_history_tool` | 3 | Recent commits with risk flags (endpoint_rename, migration, auth_change, …) |
| `scan_logs_tool` | 4 | Find `ERROR`/`FATAL` lines in `*.log` files |
| `scan_config_tool` | 5 | Read `.env`, `docker-compose.yml`, `CHANGELOG.md`, etc. |
| `correlate_evidence` | 6 | Build correlation matrix + failure clusters |
| `form_hypotheses_tool` | 7 | Ranked hypotheses with confidence + remediation |
| `render_report` | 8 | Render the final report as Markdown / JSON |
| `create_github_issue` | — | File the top hypothesis as a GitHub issue |
| `analyze` | 1–8 | One call that runs the entire pipeline |
| `list_questions` | — | Returns the questions the server may ask via elicitation |
| `server_info` | — | Diagnostic metadata |

---

## Supported test frameworks

Auto-detected by content sniff (first 4 KB). Override with `--framework <name>`.

| Framework | Input format |
|---|---|
| Playwright | `results.json` (JSON reporter) |
| pytest | `results.xml` (JUnit) or `results.json` (pytest-json-report) |
| Jest / Vitest | `--json` / `--reporter=json` output |
| Cypress | mochawesome JSON |
| WebdriverIO | mochawesome JSON or JUnit XML |
| Any | JUnit XML (generic fallback) |

Adding a new framework is one file in `analyzer/parsers/` implementing the `Parser` ABC.

---

## CI integration

This package is designed to be installed in any CI pipeline. See
[`playwright-userauth-api-suite`](https://github.com/aks-builds/playwright-userauth-api-suite)
for a complete working example. The pattern is:

```yaml
- name: Install ai-test-failure-analyzer
  if: steps.tests.outcome == 'failure'
  run: pip install git+https://github.com/aks-builds/ai-test-failure-analyzer.git

- name: Analyze failures
  if: steps.tests.outcome == 'failure'
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    GITHUB_REPOSITORY: ${{ github.repository }}
  run: |
    analyzer analyze \
      --results test-results/results.json \
      --non-interactive \
      --format markdown \
      --out analysis.md \
      --create-issue \
      --repo "${GITHUB_REPOSITORY}"
```

---

## Security model

- **Path traversal protection** — all filesystem inputs flow through `analyzer.security.safe_path`.
- **Command injection prevention** — `subprocess` calls are always `list[str]`, never `shell=True`.
- **Secrets from env only** — `GITHUB_TOKEN` and `ANALYZER_HTTP_TOKEN` never appear in CLI args or logs.
- **Bounded scans** — per-file 5 MB cap, per-scan 50 MB cap, ≤ 200 commits, ≤ 6 directory levels.
- **HTTP transport is loopback by default** — non-loopback requires `ANALYZER_HTTP_TOKEN`.
- **`.env` redaction** — token/secret/key/password values are redacted in all outputs.

---

## Architecture

```
                ┌────────────────────────────────────────────────────┐
                │              orchestrator.analyze()                 │
                │  chains all 8 phases, emits progress events        │
                └──────┬───────────┬───────────┬──────────┬──────────┘
                       ▼           ▼           ▼          ▼
                  parsers      evidence    correlator  hypothesis
                       │           │           │          │
        ┌──────────────┴───────────┴───────────┴──────────┘
        ▼              ▼                  ▼                ▼
  MCP stdio       MCP HTTP           CLI / TUI         FastAPI
  (Claude Code,   (OpenAI,           (questionary       Web UI
   Cursor)         Gemini)            + rich)           (HTMX)
```

All interfaces call the **same** `orchestrator.analyze()` — no special-casing per transport.

---

## Project structure

```
ai-test-failure-analyzer/
├── analyzer/
│   ├── server.py              FastMCP server (stdio + streamable-http)
│   ├── orchestrator.py        analyze() — chains the 8 phases
│   ├── parsers/               one file per test framework
│   ├── evidence/              git_scan, log_scan, config_scan, correlator
│   ├── hypothesis.py          scoring + dataclasses
│   ├── render/                markdown.py + ansi.py
│   ├── github_integration.py  PyGithub wrapper
│   ├── security.py            safe_path, arg whitelists, size caps
│   ├── config.py              pydantic settings, env-only secrets
│   ├── elicit.py              clarifying-question definitions
│   └── ui/
│       ├── cli.py             questionary + rich
│       ├── tui.py             Textual app
│       └── web/               FastAPI + Jinja2 + HTMX
├── .github/workflows/
│   └── ci.yml                 pytest + optional on-demand analysis
├── tests/
│   └── analyzer/              pytest unit tests (parsers, correlator, security)
├── pyproject.toml
├── SKILL.md                   Manual fallback runbook (8-phase walkthrough)
└── README.md
```

---

## Verifying the package

```bash
pip install -e .
pytest tests/analyzer -q          # unit tests: parsers, correlator, security
analyzer info                     # server metadata
```

---

## Contributing

**New framework parser:** create `analyzer/parsers/<name>.py` subclassing `Parser`,
implement `can_parse(sample)` and `parse(path) → list[NormalizedFailure]`,
register in `analyzer/parsers/__init__.py`, add a fixture + test.

**New MCP tool:** add a method decorated `@mcp.tool()` in `analyzer/server.py`.
Return a dict with an `evidence` list for explainability.

---

## Related

- **[`playwright-userauth-api-suite`](https://github.com/aks-builds/playwright-userauth-api-suite)** —
  the NashLearn demo test repo. Ships with three intentional failures; its CI installs this package
  and produces a full root-cause report automatically.

---

## License

MIT.
