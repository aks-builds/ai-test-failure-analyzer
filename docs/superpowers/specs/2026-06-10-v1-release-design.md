# ai-test-failure-analyzer v1.0.0 — Release Design

**Date:** 2026-06-10
**Deadline:** 2026-06-14 (Saturday)
**Status:** Approved — ready for implementation

---

## Goal

Ship `ai-test-failure-analyzer` as a production-quality, globally-installable tool on npm, PyPI, and as a Claude Code skill. Fix evidence contamination (fixture noise, hypothesis repetition, wrong root cause cycling), add API-only mode for source-free workspaces, add Newman and k6 parsers, and deliver a beautiful README matching cliproof's standard.

---

## Section 1 — Architecture

### Problem being fixed

The current tool points to test fixture files and "intentional failure" comments as root causes, and repeats the same wrong hypothesis across report sections and across runs. When no source code is available (API automation with public APIs), the tool has no defined behavior.

### Solution: Evidence Tiers + Noise Filter + API-Only Mode

#### Phase 0 — Workspace Scanner (new file: `analyzer/workspace_scanner.py`)

Runs before Phase 1. Returns a `WorkspaceProfile` dataclass passed through all subsequent phases.

```python
@dataclass
class WorkspaceProfile:
    mode: Literal["FULL_SOURCE", "API_ONLY"]
    source_roots: list[Path]   # src/, app/, lib/, api/ — Tier-1 evidence dirs
    test_roots: list[Path]     # tests/, test/, spec/, e2e/ — Tier-2 context only
    noise_paths: list[Path]    # tests/fixtures/, **/__mocks__/ — blocked entirely
    openapi_spec: Path | None  # openapi.yaml / swagger.json if found
    has_git: bool
```

**Mode detection logic:**
- If any of `src/`, `app/`, `lib/`, `api/` exist → `FULL_SOURCE`
- If `--mode api-only` flag passed → `API_ONLY` (forced)
- Otherwise → `API_ONLY`

**Noise path detection:** Any directory named `fixtures`, `__mocks__`, `__fixtures__`, `testdata`, or `test-data` under a test root is added to `noise_paths`.

#### Evidence Tier Assignment

Applied during Phases 3–5 (git scan, log scan, config scan).

| Tier | FULL_SOURCE | API_ONLY |
|------|-------------|----------|
| Tier-1 (root cause eligible) | `source_roots` files, app logs, git commits touching source_roots, .env / docker-compose | HTTP status code, response body, response headers, OpenAPI spec |
| Tier-2 (context only, never root cause) | `test_roots` files | Prior run history |
| Blocked (never used) | `noise_paths`, files matching noise keywords | N/A |

#### Noise Filter (new file: `analyzer/noise_filter.py`)

Runs during Phase 6 (correlator), before hypothesis formation. Four rules applied in order:

1. **Path block** — evidence item path is under `noise_paths` → DROP
2. **Keyword block** — evidence text contains any of: `intentional`, `on purpose`, `expected to fail`, `demo`, `fixture`, `deliberately` (case-insensitive) → DROP
3. **Deduplication** — hypothesis fingerprint (SHA1 of title + root file) already seen this run → DROP
4. **Tier-1 gate** (FULL_SOURCE only) — hypothesis has zero Tier-1 evidence items → SUPPRESS, output `"⚠ No application-layer fault detected."` instead

The keyword list is configurable via `.atfa/noise-keywords.json` in the workspace root.

#### API-Only Hypothesis Types

When `mode == API_ONLY`, Phase 7 maps HTTP evidence to predefined, evidence-grounded hypothesis templates:

| Status | Hypothesis title | Evidence cited |
|--------|-----------------|----------------|
| 404 / 410 | Endpoint moved or removed | URL + status code |
| 401 / 403 | Auth failure — token expired, wrong scope, or IP-restricted | Status + `WWW-Authenticate` / `X-Error` headers |
| 429 | Rate limit exceeded | Status + `Retry-After` header |
| 500 / 502 / 503 | Server-side fault — not actionable from client | Status + response body excerpt |
| Schema mismatch | Response body missing expected fields | Field diff against OpenAPI spec |
| Timeout / ECONNREFUSED | Network or infra fault | Host + port + error type |

No hypothesis is formed without at least one of these Tier-1 HTTP evidence items. If no HTTP data is extractable, the report states `"⚠ Insufficient HTTP evidence to conclude."` — never a guess.

#### Report Mode Banner

Every report opens with:
- `FULL_SOURCE mode — scanned src/, git history, logs, config`
- `API_ONLY mode — no workspace source detected, analyzing HTTP contract only`

---

## Section 2 — Parser Ecosystem

All parsers produce `NormalizedFailure` — unchanged schema, `http.*` fields populated for API-only hypotheses.

### New parsers

#### `analyzer/parsers/newman_json.py`

**Triggered by:** top-level keys contain `collection` + `run` + `executions`

**Extraction:**
- `item.name` → `suite` / `title`
- `request.method` + `request.url.raw` → `http.method` + `http.url`
- `response.code` → `http.status_code`
- `response.responseTime` → `http.response_time_ms`
- `assertions[n].error.message` (failed only) → `error_msg`
- `file` / `line` → `None` (API-only, no source file)

#### `analyzer/parsers/k6_json.py`

**Triggered by:** top-level keys contain `root_group` + `metrics`

**Extraction (from `root_group.checks[]` recursively):**
- `check.name` → `title`; `suite` = `"k6 load test"`
- `check.fails > 0` → `status: failed`
- `"N/Y runs failed"` → `error_msg`
- `metrics.http_req_duration.values.p(95)` → `http.response_time_ms`
- `file` / `line` → `None`

### Updated auto-detect order (`parsers/__init__.py`)

1. `playwright_json` — sniff: `config` + `suites` + `specs`
2. `newman_json` — sniff: `collection` + `run` + `executions` *(new)*
3. `k6_json` — sniff: `root_group` + `metrics` *(new)*
4. `jest_json` — sniff: `testResults[].testFilePath`
5. `cypress_json` — sniff: `stats` + `results` (mochawesome)
6. `pytest_junit` — sniff: XML + pytest attributes
7. `junit_generic` — fallback for any JUnit XML (covers REST Assured, Karate, Insomnia CLI, TestNG)

**REST Assured:** Outputs standard JUnit XML. Covered by `junit_generic`. Add REST Assured error pattern recognition to `junit_generic.py`: `"N expectation(s) failed"` → parse `Expected:` / `Actual:` lines into `error_msg`.

### Tests required

- `tests/analyzer/fixtures/newman_results.json` — sample Newman run with 1 failed assertion
- `tests/analyzer/fixtures/k6_results.json` — sample k6 summary with 1 failed check
- `tests/analyzer/test_parsers.py` — extend with Newman + k6 test cases
- `tests/analyzer/test_noise_filter.py` — new test file
- `tests/analyzer/test_workspace_scanner.py` — new test file

---

## Section 3 — Distribution

### Package naming

| Channel | Package name | CLI command |
|---------|-------------|-------------|
| npm | `ai-test-failure-analyzer` | `ai-analyze` |
| PyPI | `ai-test-failure-analyzer` (rename from `qa-test-failure-analyzer`) | `analyzer` |
| Claude skill | `ai-test-failure-analyzer` | invoked via `SKILL.md` / MCP |

### New / updated files

**New JS:**
- `bin/cli.js` — zero npm-dep Node wrapper. Checks Python ≥ 3.10 → checks `analyzer` importable (auto-installs via pip if missing) → proxies all args to `python -m analyzer`. Provides `ai-analyze` command.
- `package.json` — `name: "ai-test-failure-analyzer"`, `version: "1.0.0"`, `bin: { "ai-analyze": "bin/cli.js" }`, `engines: { node: ">=18" }`, `files: ["bin/", "skills/", "README.md", "LICENSE"]`
- `.npmignore` — excludes `analyzer/`, `tests/`, `.github/`, `__pycache__/`, `*.pyc`, `pyproject.toml`

**New plugin manifests:**
- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

**Skill restructure:**
- Move `SKILL.md` → `skills/ai-test-failure-analyzer/SKILL.md`
- Update all internal references

**Updated Python:**
- `pyproject.toml` — rename `name` from `qa-test-failure-analyzer` to `ai-test-failure-analyzer`; add `build-system` table for twine compatibility

### CI / CD workflows

#### `.github/workflows/release.yml` (new — mirrors cliproof exactly)

Triggered: manual dispatch with `bump` input (`patch` / `minor` / `major` / `prerelease`)

Steps:
1. `npm version $bump --no-git-tag-version`
2. Sync new version into `pyproject.toml`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
3. Roll `CHANGELOG.md`: `[Unreleased]` → `[X.Y.Z] - DATE`
4. Push branch `release/vX.Y.Z`, open PR against `main` with auto-merge enabled
5. Uses `RELEASE_PR_PAT` (not `GITHUB_TOKEN`) so downstream CI triggers

#### `.github/workflows/publish.yml` (new)

Triggered: `release/*` PR merges into `main`

Three jobs (publish-npm → publish-pypi → github-release):

1. **publish-npm** — `npm publish --provenance`; dist-tag `latest` (stable) or `alpha` (pre-1.0)
2. **publish-pypi** — `python -m build && twine upload dist/*` using `PYPI_TOKEN`
3. **github-release** — needs job1 + job2; tags `vX.Y.Z`, extracts CHANGELOG notes, creates GitHub release

Required secrets: `NPM_TOKEN`, `PYPI_TOKEN`, `RELEASE_PR_PAT`

#### `.github/workflows/ci.yml` (update existing)

- Add aggregate `test` gate job (matrix: Python 3.10, 3.11, 3.12) — required for branch protection
- Add `npm test` job (Node ≥ 18) — smoke-tests `bin/cli.js` passthrough
- Keep existing pytest steps; add `test_noise_filter.py`, `test_workspace_scanner.py`

#### `.github/workflows/codeql.yml` (new)

Standard CodeQL security scanning for Python.

---

## Section 4 — README

### Top section (matches cliproof style)

```
🩻 ai-test-failure-analyzer
────────────────────────────────
Root cause in seconds. Evidence, not intuition.

Feed it a real test result file — Playwright, Jest, Cypress, Newman, k6, or JUnit —
and it traces back through your real git history, application logs, and config
to surface the actual root cause, with a cited evidence chain and file:line precision.
No guesses. No fixture noise. No repeating the obvious.

[CI passing] [CodeQL passing] [npm v1.0.0] [PyPI v1.0.0] [MIT] [MCP server] [Agent Skill]

[terminal hero image: ai-analyze analyze playwright-report.json running all 8 phases,
 ending with Root Cause [92%] api/routes.py:44]

🩻 A real analysis — evidence from git, app.log, and .env — no guesses, no fixture noise.
```

### Hero terminal output (SVG generated via cliproof / freeze)

Shows `ai-analyze analyze playwright-report.json` running:
- All 8 phases with real counts
- Phase 6 showing "1 noise item filtered"
- Phase 7 showing "1 confirmed · 1 suppressed (no Tier-1)"
- Root Cause block at 92% confidence with `api/routes.py:44` and evidence citation

### README sections (after hero)

1. **Why ai-test-failure-analyzer** — the fixture-noise problem, the triage time problem
2. **How it's different** — comparison table vs manual triage vs generic LLM
3. **Supported frameworks** — table of 8 frameworks with install commands
4. **Install** — three paths: npm global, pipx, Claude skill
5. **Usage** — CLI, MCP stdio, MCP HTTP, API-only mode
6. **API-only mode** — explicit section for Newman/k6/no-source use case
7. **Security** — path traversal, size caps, secrets redaction
8. **Repository layout** — tree
9. **Testing** — test count, frameworks, CI matrix
10. **Contributing**

---

## Saturday Checklist

### New Python files (4)
- [ ] `analyzer/workspace_scanner.py`
- [ ] `analyzer/noise_filter.py`
- [ ] `analyzer/parsers/newman_json.py`
- [ ] `analyzer/parsers/k6_json.py`

### Updated Python files (4)
- [ ] `analyzer/orchestrator.py` — pass `WorkspaceProfile` through all phases
- [ ] `analyzer/parsers/__init__.py` — update auto-detect order
- [ ] `analyzer/parsers/junit_generic.py` — REST Assured error pattern
- [ ] `analyzer/hypothesis.py` — Tier-1 gate, dedup by fingerprint

### New JS / config (5)
- [ ] `bin/cli.js`
- [ ] `package.json`
- [ ] `.npmignore`
- [ ] `.claude-plugin/plugin.json`
- [ ] `.claude-plugin/marketplace.json`

### New CI workflows (3)
- [ ] `.github/workflows/release.yml`
- [ ] `.github/workflows/publish.yml`
- [ ] `.github/workflows/codeql.yml`

### Updated CI (1)
- [ ] `.github/workflows/ci.yml` — aggregate gate + Node job

### Skill restructure (1)
- [ ] `skills/ai-test-failure-analyzer/SKILL.md` (move from root)

### Docs / meta (4)
- [ ] `README.md` — full rewrite
- [ ] `CHANGELOG.md` — add Unreleased section
- [ ] `pyproject.toml` — rename package
- [ ] `SECURITY.md` — create (threat model: path traversal, size caps, secrets redaction, no network calls)
- [ ] `CONTRIBUTING.md` — create (dev setup, commit style, releasing)

### Tests (3 new files)
- [ ] `tests/analyzer/test_noise_filter.py`
- [ ] `tests/analyzer/test_workspace_scanner.py`
- [ ] `tests/analyzer/fixtures/newman_results.json`
- [ ] `tests/analyzer/fixtures/k6_results.json`
- [ ] Extend `tests/analyzer/test_parsers.py` with Newman + k6

---

## Out of scope (v2)

- Backward fault trace (approach C) — tracing test call chain into app AST
- Artillery / Gatling parsers
- Freshness check workflow (no proof manifest yet)
