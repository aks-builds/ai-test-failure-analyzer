# Skill: Analyse Test Failures

> ⚠️ **This runbook is the manual fallback.**
> The preferred path is the **QA Test Failure Analyzer MCP server** (`analyzer analyze`, or any MCP
> client like Claude Code, Cursor, OpenAI, Gemini connected to `analyzer serve-stdio`/`serve-http`).
> The 8 phases below are mirrored 1-to-1 by MCP tools:
> Phase 1 → `collect_failures` · Phase 2 → `read_test_intent` · Phase 3 → `scan_git_history_tool`
> · Phase 4 → `scan_logs_tool` · Phase 5 → `scan_config_tool` · Phase 6 → `correlate_evidence`
> · Phase 7 → `form_hypotheses_tool` · Phase 8 → `render_report`.
> Follow this document only when the MCP server is unavailable.

> **Session context** — NashLearn: "AI-Assisted Test Failure Analysis"
> This skill eliminates the single most time-consuming and frustrating part of running a
> test suite at scale: **understanding why something failed**.
> Instead of 30–60 minutes of manual digging through logs, git history, Slack threads, and
> deployment records, an AI agent correlates the same evidence in seconds and delivers
> actionable root cause hypotheses backed by a traceable evidence chain.

---

## Purpose & Invocation

Use this skill whenever automated tests have failed and you need to understand *why*.

**Trigger phrases (say any of these to Claude Code):**
- "Analyse the failing tests"
- "Why did the tests fail?"
- "Investigate the test failures"
- "Run a root cause analysis on the failures"
- "Follow SKILL.md"

**Scope:** API failures, frontend failures, backend failures, database failures,
infrastructure failures — any automated test that produces structured output.
For this demo the suite is a Playwright API test set.

---

## What This Skill Does (the narrative for the audience)

A developer runs the CI pipeline. Tests go red. The classic response is:
1. Open the failure log, stare at a stack trace.
2. Ask around: "Did anything deploy recently?"
3. Check Jira, Slack, the deployment dashboard — separately, manually.
4. Eventually connect the dots. Maybe 45 minutes later. Maybe never.

This skill replaces steps 1–4 with a single, systematic AI investigation that:
- Reads **every** failing test and its expected behaviour
- Scans **all** recent code and config changes
- Checks **any** available logs and deployment artefacts
- **Cross-correlates** all evidence to surface causal chains
- Produces **ranked hypotheses** with confidence scores and concrete fix steps

The audience should see Claude moving through real evidence — not a canned script —
and arriving at the same conclusions a senior engineer would reach, in a fraction of the time.

---

## Investigation Procedure

Work through all eight phases in order.
Print a visible heading before each phase so the audience can follow along.

---

### Phase 1 — Collect the Failures

Read `test-results/results.json` (Playwright JSON reporter output).

Extract for **every failing test**:
- Test title / name
- Source file (spec file path)
- Endpoint or action under test
- HTTP status received vs expected (or error message if non-HTTP)
- Error text / assertion message

Print a **Failure Triage Table** like this:

```
┌─ FAILURE TRIAGE ─────────────────────────────────────────────────────┐
│ # │ Test                              │ Endpoint          │ Got │ Exp │
│ 1 │ login returns token…              │ GET /auth/session  │ 404 │ 200 │
│ 2 │ register new account…             │ POST /register/… │ 404 │ 201 │
│ 3 │ get user by id from staging…      │ GET /users/9999   │ 404 │ 200 │
└───────────────────────────────────────────────────────────────────────┘
  3 failing  |  3 passing  |  6 total
```

If `test-results/results.json` does not exist, note it and ask the user to run
`npx playwright test` first.

---

### Phase 2 — Understand the Test Intent

For each failing test, read its source `.spec.ts` (or `.spec.js`, `_test.go`, etc.).

Extract:
- The **endpoint path or action** being tested (exact string, not inferred)
- The **expected behaviour** (status code, response shape, data)
- Any **inline comments** — these are intentional developer notes and often
  contain the most important evidence (deployment version, what changed, when)
- Any **hardcoded values** (IDs, URLs, tokens) that could be stale

Also read `playwright.config.ts` (or equivalent test config) for:
- `baseURL` — is it pointing at the right environment?
- Timeout settings — are failures timing out or returning wrong status?
- Any environment variable references

> 💡 **Demo note:** The spec files in this project contain rich comments describing
> the v2.3.1 breaking changes. These comments are the primary evidence source —
> read them carefully and cite them in your hypotheses.

---

### Phase 3 — Scan Recent Code & Config Changes

Run the following git commands and report findings:

```bash
# Recent commit history
git log --oneline -20

# Commits in the last 48 hours
git log --oneline --since="48 hours ago"

# Recent changes to source and config files
git diff HEAD~5 -- "*.ts" "*.js" "*.json" "*.yaml" "*.yml" "*.env*" "*.config.*"

# Changes specifically to test config
git log --oneline -- playwright.config.ts tsconfig.json package.json

# Changes to tests themselves
git log --oneline -- tests/

# Show full diff for any high-risk commits (endpoint changes, config changes, migrations)
git show <commit-hash> --stat
```

Flag commits as **HIGH RISK** if they contain:
- Endpoint/route renames or restructuring
- Database schema changes or migrations
- Configuration value changes (pool sizes, timeouts, base URLs)
- Dependency upgrades
- Authentication/session changes
- Test fixture or seed data changes

If git history is sparse (new repo or few commits), note it and weight other
evidence sources more heavily — do not block on empty git log.

---

### Phase 4 — Scan Logs and Deployment Artefacts

Check for log files in standard locations:

```bash
# Application log files
find . -name "*.log" -not -path "*/node_modules/*" 2>/dev/null
ls logs/ log/ 2>/dev/null

# Docker Compose logs (if running)
docker compose logs --tail=100 2>/dev/null

# CI artefacts
ls .github/workflows/ .circleci/ .gitlab-ci.yml 2>/dev/null

# Any crash dumps or error outputs
find . -name "*.dump" -o -name "crash*.txt" 2>/dev/null | head -20
```

If log files exist, scan them for:
- ERROR or FATAL lines near the time the tests ran
- Stack traces matching the failing services
- Connection refused / timeout messages
- Configuration loaded messages (shows what values are actually in use)

If no logs exist, note that absence explicitly — it's still useful information
("No application logs available — analysis relies on test output and source code").

---

### Phase 5 — Environment & Configuration Context

Check for environment and deployment context:

```bash
# Environment files
cat .env 2>/dev/null || echo "(no .env file)"
cat .env.example 2>/dev/null || echo "(no .env.example)"
cat .env.local 2>/dev/null || echo "(no .env.local)"

# Service configuration
cat docker-compose.yml 2>/dev/null || echo "(no docker-compose.yml)"
ls config/ 2>/dev/null

# Changelog / release notes
cat CHANGELOG.md 2>/dev/null | head -80
cat RELEASES.md 2>/dev/null | head -80

# Package / dependency changes
git diff HEAD~5 -- package.json requirements.txt go.mod Gemfile 2>/dev/null
```

Look for:
- Base URL pointing at wrong environment (staging vs production vs mock)
- Missing or changed environment variables
- Service version mismatches
- Recent dependency upgrades that could affect behaviour

---

### Phase 6 — Cross-Correlate Evidence

Build a **Correlation Matrix** — one row per failing test, one column per evidence source:

```
┌─ EVIDENCE CORRELATION MATRIX ──────────────────────────────────────────────────────────┐
│ Test                    │ Endpoint        │ Status │ Code Comment    │ Git    │ Config  │
│ login returns token…    │ GET /auth/sess  │ 404    │ ✅ v2.3.1 rename │ ✅ ?   │ —       │
│ register new account…   │ POST /register  │ 404    │ ✅ v2.3.1 move   │ ✅ ?   │ —       │
│ get user by id…         │ GET /users/9999 │ 404    │ ✅ DB migration  │ ✅ ?   │ ✅ id   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**Pattern recognition — what to look for:**

| Pattern | Likely cause |
|---------|-------------|
| Multiple tests → same HTTP 404 on different endpoints | Deployment broke routing |
| All auth tests fail, user tests pass | Auth-service specific regression |
| Tests fail with 404 on specific IDs/paths | Stale hardcoded test data or deleted records |
| All tests timeout, none get a response | Service is down, wrong baseURL, or network issue |
| Tests fail on POST but pass on GET | Permission/auth regression, schema change |
| Frontend tests fail after API tests pass | API contract mismatch (frontend calling wrong version) |
| Flaky failures (some pass, some fail) | Race condition, connection pool exhaustion |

**Grouping:** Cluster failures that share a root cause. Two tests broken by the same
deployment change count as one root cause, not two.

---

### Phase 7 — Form Root Cause Hypotheses

For each distinct failure cluster, produce one hypothesis.

**Format:**

```
╔══ HYPOTHESIS [N] — [Service / Component] ══════════════════════════════╗
║  Confidence : [X]%  ([justification])
║  Root Cause : [One sentence. What broke, why, and what effect it has.]
║
║  Evidence Chain:
║    🎭 Test output  : [what the test saw — status code, error message]
║    📄 Source code  : [relevant line from spec file or comment]
║    🔀 Git history  : [commit hash and message, if available]
║    📋 Logs         : [log evidence, or "no logs available"]
║    ⚙️  Config       : [config value or env var, if relevant]
║
║  Affected Tests:
║    ❌ [test title 1]
║    ❌ [test title 2]
║
║  Remediation:
║    1. [Specific, actionable fix — name the file and what to change]
║    2. [Verification step — how to confirm the fix works]
║    3. [Preventive measure — how to stop this happening again]
║
║  Buggy location : [filename]:[approximate line] ← commit [hash]
╚════════════════════════════════════════════════════════════════════════╝
```

**Confidence scoring guide:**

| Score | Meaning |
|-------|---------|
| 90–99% | Multiple independent sources agree; the causal chain is complete |
| 70–89% | Strong evidence from 2+ sources; minor uncertainty remains |
| 50–69% | Single strong evidence source; plausible but not confirmed |
| 30–49% | Circumstantial; worth investigating but needs verification |
| <30%   | Speculative; flag as "needs more data" |

> **Honesty rule:** Never inflate confidence to sound impressive. A 72% with clear
> reasoning is more credible to a technical audience than an unjustified 97%.

---

### Phase 8 — Produce the Final Report

Format the complete report as:

```
════════════════════════════════════════════════════════════
  🤖  TEST FAILURE ROOT CAUSE ANALYSIS REPORT
════════════════════════════════════════════════════════════

SUMMARY
  Failing : X  |  Passing : Y  |  Total : Z
  Root cause clusters : N
  Analysis completed  : [timestamp]
  Evidence sources consulted:
    ✅ Test results (test-results/results.json)
    ✅ Test source  (tests/playwright/*.spec.ts)
    ✅ Test config  (playwright.config.ts)
    ✅ Git history  (git log)
    [✅/❌] Application logs
    [✅/❌] Environment config

─────────────────────────────────────────────────────────────
ROOT CAUSE HYPOTHESES  (ranked by confidence)
─────────────────────────────────────────────────────────────

[Hypothesis cards here — see Phase 7 format]

─────────────────────────────────────────────────────────────
IMPACT
─────────────────────────────────────────────────────────────
  Typical manual investigation time : ~30–60 minutes
  AI-assisted analysis time         : [actual elapsed time]
  Evidence sources cross-correlated : [count]

  The agent read the same evidence a human engineer would.
  It didn't skip a source. It didn't miss a commit.
  It connected dots across [N] data sources simultaneously.

─────────────────────────────────────────────────────────────
RECOMMENDED NEXT STEPS
─────────────────────────────────────────────────────────────
  1. [Most critical fix — specific file and change]
  2. [Secondary fix]
  3. [Preventive measure — process or tooling improvement]
════════════════════════════════════════════════════════════
```

---

## Guidance by Failure Type

### API Test Failures (HTTP endpoints)
Primary evidence sources: test output → spec comments → git log → deployment notes
Key questions:
- Does the endpoint exist at all? (404 = missing or renamed)
- Did the endpoint path change recently? (look for route refactors in git)
- Is the base URL correct? (staging vs prod vs mock)
- Did the request schema change? (POST body, headers, auth tokens)
- Was test data deleted or migrated? (hardcoded IDs returning 404)

### Frontend Test Failures (Playwright UI / Cypress / Selenium)
Primary evidence sources: screenshots → console errors → network requests → DOM assertions
Key questions:
- Did the API contract change? (frontend calling old endpoint version)
- Did a CSS selector or element ID change? (selector-based test fragility)
- Did a feature flag disable the feature under test?
- Is there a JavaScript error in the browser console during the test?
- Did a build or bundler change break asset loading?

### Database / ORM Failures
Primary evidence sources: error messages → migration files → connection config
Key questions:
- Did a schema migration run that changed column names or constraints?
- Was test data seeded/refreshed correctly?
- Did connection pool settings change?
- Are credentials or connection strings still valid?

### Infrastructure / Network Failures
Primary evidence sources: timeout errors → logs → deployment config
Key questions:
- Is the target service actually running?
- Did a firewall rule or network policy change?
- Did a DNS entry change or expire?
- Did a TLS certificate expire?
- Did a port mapping change (Docker, Kubernetes)?

---

## Quality Criteria for a Good Analysis

A high-quality root cause analysis:

✅ **Cites specific evidence** — names the file, line, commit, or log entry  
✅ **Explains the causal chain** — what broke → why it broke → how it caused the test failure  
✅ **Covers ALL failures** — does not skip the "smaller" ones  
✅ **Groups related failures** — does not treat symptoms as separate root causes  
✅ **Provides actionable fixes** — names the file and what to change, not "investigate further"  
✅ **Is honest about uncertainty** — calibrated confidence scores, not all 95%+  
✅ **Is fast to read** — a senior engineer scanning the report should understand it in under 2 minutes  
✅ **Considers alternatives** — if two hypotheses are plausible, note both  

A poor analysis:
❌ Repeats the error message without explaining the cause  
❌ Says "the test failed because the endpoint returned 404" (that's what the failure IS, not the cause)  
❌ Assigns 95% confidence to everything  
❌ Produces a wall of text without structure  
❌ Ignores the git history or available code comments  

---

## Demo Talking Points (for the presenter)

Use these to narrate what Claude is doing as the audience watches:

> **"Phase 1"** — "Claude is reading the raw test output, same as you'd see in your CI terminal."

> **"Phase 2"** — "Now it's reading the test source — not just the error, but what the developer
> *intended* the test to check, including any notes they left in comments."

> **"Phase 3"** — "This is where it gets interesting. Claude is running actual git commands against
> this repository — the same commands you'd run if you were debugging manually."

> **"Phase 6"** — "Cross-correlation: Claude is now connecting the dots across all five evidence
> sources simultaneously. This is what takes a human 30–45 minutes."

> **"Phase 8"** — "And here's the report. Three distinct root causes, ranked by confidence,
> each with a traceable evidence chain and specific fix steps. All from real data. No script."
