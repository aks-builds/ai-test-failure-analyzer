# QA Test Failure Analyzer

> An **MCP (Model Context Protocol) server** that performs AI-assisted root-cause analysis on failed test runs.
> Works with **Playwright, pytest, Jest/Vitest, Cypress, and WebdriverIO**. Callable from any MCP-capable AI client (Claude Code, Cursor, OpenAI, Gemini), as a CLI, as a TUI, as a local web dashboard, and from GitHub Actions.

---

## What problem does this solve?

The single most time-consuming and frustrating part of running a test suite at scale is **understanding why something failed**. Engineers spend 30–60 minutes per regression triaging logs, git history, deployment notes, and Slack threads — often only to discover the cause was a renamed endpoint or a stale fixture.

This project **automates that triage**:

1. Parses the test report (Playwright JSON, pytest JUnit XML, Jest JSON, Cypress JSON, …)
2. Reads recent git history with risk-pattern flagging
3. Scans application logs for `ERROR`/`FATAL` lines
4. Reads environment / config / changelog files
5. **Cross-correlates** all of the above into failure clusters
6. Produces **ranked root-cause hypotheses** with confidence scores and concrete fix steps
7. Optionally **creates a GitHub issue** with the top hypothesis

All in seconds. With a traceable evidence chain for every claim.

---

## Quick start (single command)

```bash
npm install
npm run setup:python          # one-time: pip install -e .
npx playwright install chromium

npm run analyze               # ← this is the whole demo
```

What you'll see:

1. Playwright runs (3 tests fail by design — they simulate a v2.3.1 deployment regression).
2. The analyzer's CLI takes over: triage table, eight phase headings with progress, then ranked hypothesis cards with confidence bars.
3. A clarifying question: *"Create a GitHub issue for the top hypothesis?"* — answer yes for live (needs `GITHUB_TOKEN`) or no for a dry-run preview.

---

## The five ways to use it

| Mode | Command | Best for |
|---|---|---|
| **CLI** | `npm run analyze` (or `analyzer analyze`) | Live demos, day-to-day local triage |
| **TUI** | `npm run analyze:tui` | Polished terminal UI for screen-share |
| **Web** | `npm run analyze:web` | Browser dashboard at `http://127.0.0.1:8765` |
| **MCP (stdio)** | `analyzer serve-stdio` | Claude Code, Cursor, any local MCP client |
| **MCP (HTTP)** | `analyzer serve-http --port 8765` | OpenAI, Gemini, remote AI clients |
| **CI** | GitHub Actions workflow | Auto-creates issue when CI tests fail |

---

## Using it from any AI client

### Claude Code / Cursor (stdio)

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

Then in chat: *"Analyse the failing tests in this repo."* Claude will call `analyze` (or the individual phase tools) directly.

### OpenAI / Gemini / any HTTP MCP client

Start the server:

```bash
analyzer serve-http --host 127.0.0.1 --port 8765
```

For non-loopback access, set `ANALYZER_HTTP_TOKEN` and clients must send `Authorization: Bearer <token>`.

The server speaks the standard MCP streamable-HTTP transport — point any compliant client at `http://127.0.0.1:8765/mcp`.

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
| `create_github_issue` | – | File the top hypothesis as a GitHub issue (dry-run default) |
| `analyze` | 1–8 | One call that does the entire flow with elicitation |
| `list_questions` | – | Returns the questions the server may ask via elicitation |
| `server_info` | – | Diagnostic metadata |

---

## Supported test frameworks

Auto-detection by content sniff (first 4 KB). You can also pass `--framework <name>` to skip detection.

| Framework | Input format | Notes |
|---|---|---|
| Playwright | `results.json` (JSON reporter) | Primary demo target |
| pytest | `results.xml` (JUnit) or `results.json` (pytest-json-report) | Both supported |
| Jest | `--json` output | Same shape as Vitest |
| Vitest | `--reporter=json` output | |
| Cypress | mochawesome JSON | |
| WebdriverIO | mochawesome JSON or JUnit XML | |
| Any | JUnit XML | Generic fallback |

Adding a new framework is one file in `analyzer/parsers/` implementing the `Parser` ABC.

---

## GitHub Actions integration

`.github/workflows/analyze-failures.yml` is included. On every PR / push to `main`:

1. Runs the Playwright suite.
2. If anything fails, runs `analyzer analyze --create-issue`.
3. Comments the full analysis on the PR.
4. Uploads `analysis.md` as a workflow artifact.

Required permissions (set in the workflow): `contents: read`, `issues: write`, `pull-requests: write`. `GITHUB_TOKEN` is the workflow-issued token — no extra secrets needed.

---

## Security model

This is built to run as a server, so the security primitives matter:

- **Path traversal protection** — every filesystem input flows through `analyzer.security.safe_path`, which rejects paths that escape the workspace root or follow symlinks out.
- **Command injection prevention** — `subprocess` calls are always `list[str]`, never `shell=True`. Git subcommands are whitelisted; commit hashes are regex-validated.
- **Secrets from env only** — `GITHUB_TOKEN` and `ANALYZER_HTTP_TOKEN` come from environment variables. They never appear in CLI args, log lines, or `__repr__`.
- **Bounded scans** — per-file 5 MB cap, per-scan 50 MB cap, per-log-line 4 KB cap, ≤ 200 commits, ≤ 6 directory levels.
- **HTTP transport is loopback by default** — binding non-loopback requires `ANALYZER_HTTP_TOKEN`; clients must send `Authorization: Bearer <token>`.
- **`.env` redaction** — values for keys containing `token`/`secret`/`key`/`password` are redacted before being embedded in any report or evidence chain.
- **HTML sanitization** — issue bodies and web responses strip raw HTML from test output before rendering.

---

## Architecture

```
                ┌────────────────────────────────────────────────────────────────┐
                │                       orchestrator.analyze()                    │
                │  (single function — chains all 8 phases, emits progress events) │
                └─────────┬─────────────┬─────────────┬───────────────┬──────────┘
                          ▼             ▼             ▼               ▼
                   ┌──────────┐  ┌──────────┐  ┌──────────┐    ┌──────────┐
                   │  parsers │  │ evidence │  │   corr.  │    │hypothesis│
                   └──────────┘  └──────────┘  └──────────┘    └──────────┘
                          │             │             │               │
   ┌──────────────────────┴─────────────┴─────────────┴───────────────┘──────────┐
   │                                                                              │
   ▼                          ▼                          ▼                        ▼
┌────────────┐         ┌────────────┐            ┌────────────┐         ┌────────────┐
│  MCP stdio │         │  MCP HTTP  │            │  CLI / TUI │         │   FastAPI  │
│ (Claude C, │         │ (OpenAI,   │            │  / `npm    │         │   Web UI   │
│  Cursor)   │         │  Gemini)   │            │   run`)    │         │ (HTMX)     │
└────────────┘         └────────────┘            └────────────┘         └────────────┘

                              + GitHub Actions workflow
                                → calls `analyzer analyze`
                                → creates issues / PR comments
```

All UIs and transports call the **same** `orchestrator.analyze()` function. The single source of clarifying questions (`analyzer/elicit.py`) is reused by MCP elicitation, the CLI's `questionary` prompts, the TUI's modal, and the web form.

---

## The demo data

This repo also ships a Playwright suite with **three intentional failures** that simulate a real v2.3.1 deployment regression — perfect for live demos:

| Test | Endpoint | Expected | Got | Documented Cause |
|---|---|---|---|---|
| `login returns token for valid credentials` | `GET /auth/session` | 200 | 404 | Endpoint renamed to `/auth/v2/session` in v2.3.1 |
| `register new account via /api/register` | `POST /register/users` | 201 | 404 | Route moved to `/api/v2/users/register` in v2.3.1 |
| `get user by id from staging config` | `GET /users/9999` | 200 | 404 | User ID 9999 purged in v2.3.1 DB migration |

The analyzer rediscovers these causes from the test output, spec comments, and (if you set up a commit history) git log — not from a script.

---

## Verifying it works

```bash
pytest tests/analyzer/                  # unit tests for parsers, correlator, security
npm run analyze                         # end-to-end against the demo data
analyzer info                           # server metadata
```

---

## Project structure

```
ai-test-failure-analyzer/
├── analyzer/                  # Python package — the MCP server lives here
│   ├── server.py              # FastMCP server (stdio + streamable-http)
│   ├── orchestrator.py        # analyze() — chains the 8 phases
│   ├── parsers/               # one file per framework
│   ├── evidence/              # git_scan, log_scan, config_scan, correlator
│   ├── hypothesis.py          # scoring + dataclass
│   ├── render/                # markdown.py + ansi.py
│   ├── github_integration.py  # PyGithub wrapper
│   ├── security.py            # safe_path, arg whitelists, size caps
│   ├── config.py              # pydantic settings, env-only secrets
│   ├── elicit.py              # single source of clarifying questions
│   └── ui/
│       ├── cli.py             # questionary + rich
│       ├── tui.py             # Textual app
│       └── web/               # FastAPI + Jinja2 + HTMX
├── .github/workflows/
│   └── analyze-failures.yml
├── tests/
│   ├── playwright/            # the demo test suite (3 intentional failures)
│   └── analyzer/              # Python unit tests
├── playwright.config.ts
├── package.json
├── pyproject.toml
├── SKILL.md                   # fallback runbook for clients that don't speak MCP
└── README.md
```

---

## Contributing

Adding a new framework parser:

1. Create `analyzer/parsers/<name>.py` subclassing `Parser`.
2. Implement `can_parse(sample)` (sniff first 4 KB) and `parse(path)` (returns `list[NormalizedFailure]`).
3. Register it in `analyzer/parsers/__init__.py` (`PARSERS` list and `FRAMEWORKS` dict).
4. Add a fixture in `tests/analyzer/fixtures/` and a test in `tests/analyzer/test_parsers.py`.

Adding a new MCP tool: add a method decorated `@mcp.tool()` in `analyzer/server.py`. Return a dict with an `evidence` list for explainability.

---

## License

MIT.
