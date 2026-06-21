# How to Run ai-test-failure-analyzer

## Requirements

- **Python 3.10–3.14** on PATH
- **Node.js 18+** (for the `ai-analyze` CLI wrapper and npm install)
- A test results file from any [supported framework](#supported-formats)

---

## Install

```bash
# npm — global install (JS/CI teams)
npm install -g ai-test-failure-analyzer

# npx — no install needed
npx ai-test-failure-analyzer analyze results.json

# pipx — Python devs
pipx install ai-test-failure-analyzer
```

Verify installation:

```bash
ai-analyze --version
ai-analyze info
```

---

## Basic usage

Point it at your test results file:

```bash
ai-analyze analyze test-results/results.json
```

The tool auto-detects your framework from the file contents and runs a 10-phase analysis:

```
Phase 0: Scan workspace
Phase 1: Collect failures
Phase 2: Read test intent
Phase 2.5: Detect flaky tests
Phase 5.5: Collect evidence (git, logs, config — parallel)
Phase 6: Cross-correlate evidence
Phase 7: Form hypotheses
Phase 8: Produce report
```

---

## All flags

### `analyze` — main command

| Flag | Description |
|------|-------------|
| `--results` / `-r` | Path to results file (default: `test-results/results.json`) |
| `--workspace` / `-w` | Repo root (default: CWD) |
| `--framework` / `-f` | Force framework: `playwright`, `jest`, `pytest`, `junit`, etc. (default: `auto`) |
| `--mode` / `-m` | `auto` or `api-only` to skip source-code scan |
| `--out` / `-o` | Write report to this file |
| `--format` | `markdown` (default), `json`, or `ctrf` |
| `--no-cache` | Skip reading and writing the 24-hour result cache |
| `--non-interactive` | Disable clarifying questions (required for CI) |
| `--enrich` | Send top hypothesis to an LLM for natural-language explanation |
| `--create-issue` | File a GitHub issue for the top hypothesis |
| `--repo` | `owner/repo` for issue creation |

### `watch` — live re-analysis

```bash
ai-analyze watch test-results/results.json
```

Polls the results file every 2 seconds and re-runs the full analysis when it changes. Press Ctrl-C to stop.

### `serve-stdio` — MCP server (Claude Code / Cursor)

```bash
ai-analyze serve-stdio
```

Add to your MCP config (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ai-test-failure-analyzer": {
      "command": "ai-analyze",
      "args": ["serve-stdio"]
    }
  }
}
```

### `serve-http` — MCP over HTTP (OpenAI / Gemini)

```bash
ai-analyze serve-http --port 8765
```

### `tui` — Textual TUI

```bash
ai-analyze tui
```

Interactive terminal dashboard. Navigate failures with arrow keys.

### `web` — Web dashboard

```bash
ai-analyze web
```

Opens a FastAPI web UI at `http://localhost:8000`.

---

## Output formats

### Markdown (default)

Rendered to terminal and optionally written to a file:

```bash
ai-analyze analyze results.json --out report.md
```

### JSON

Structured output with hypotheses, phase timings, and flaky-test list:

```bash
ai-analyze analyze results.json --format json --out report.json
```

### CTRF

[Common Test Results Format](https://ctrf.io) with per-test `ai` root-cause annotations:

```bash
ai-analyze analyze results.json --format ctrf --out report.ctrf.json
```

---

## CI integration (GitHub Actions)

```yaml
- name: Run tests
  run: npm test
  continue-on-error: true

- name: Analyze failures
  if: failure()
  run: |
    npx ai-test-failure-analyzer analyze test-results/results.json \
      --non-interactive \
      --format ctrf \
      --out failure-analysis.ctrf.json

- uses: actions/upload-artifact@v4
  if: failure()
  with:
    name: failure-analysis
    path: failure-analysis.ctrf.json
```

---

## LLM enrichment

Set up a provider key, then pass `--enrich`:

```bash
# Anthropic Claude
export ATFA_LLM_KEY=sk-ant-...
ai-analyze analyze results.json --enrich

# OpenAI
export OPENAI_API_KEY=sk-...
ai-analyze analyze results.json --enrich

# Ollama (local)
export ATFA_LLM_ENDPOINT=http://localhost:11434/api/chat
ai-analyze analyze results.json --enrich

# Custom endpoint
export ATFA_LLM_ENDPOINT=https://my-llm.internal/v1/chat/completions
export ATFA_LLM_KEY=my-key
ai-analyze analyze results.json --enrich
```

---

## Docker

```bash
docker run --rm -v $(pwd):/workspace \
  ghcr.io/aks-builds/ai-test-failure-analyzer \
  analyze /workspace/test-results/results.json
```

---

## Supported formats

| Framework | File to pass |
|-----------|-------------|
| Playwright | `test-results/results.json` (JSON reporter) |
| Jest / Vitest | `results.json` (`--json --outputFile`) |
| Cypress | Mochawesome JSON output |
| pytest | `results.xml` (`--junit-xml`) |
| Newman (Postman) | JSON reporter output |
| k6 | `--summary-export=results.json` |
| Go test | `go test ./... -json > results.json` |
| RSpec | `--format json --out results.json` |
| PHPUnit / NUnit / xUnit / MSTest | JUnit/XML output |
| Robot Framework | `output.xml` |
| Artillery / Gatling / Pact | Standard JSON output |
| Allure | `allure generate` results directory |
| CTRF | Any CTRF-compliant reporter |
| SARIF | Any SARIF-compliant scanner |

---

## Troubleshooting

**`Results file is empty`** — Your test runner didn't finish or the output path is wrong. Run the tests first and check the path.

**`Results file contains invalid JSON`** — The reporter was interrupted mid-write (common in CI timeout). Re-run the tests.

**`Python 3.10+ not found`** — Install Python 3.10–3.14 from [python.org](https://python.org) and ensure it's on PATH.

**Low confidence scores (< 20%)** — No git history or config files found. Run from inside the repo root, or pass `--workspace /path/to/repo`.

**Flaky detection firing on everything** — Clear the flaky history: `rm -rf .atfa/` and re-run.
