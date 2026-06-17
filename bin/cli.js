#!/usr/bin/env node
"use strict";
/*
 * ai-test-failure-analyzer — agent-agnostic npm CLI.
 *
 * `ai-analyze install`  — copy skill into every detected AI agent's skills dir.
 * `ai-analyze <cmd>`    — verify Python 3.10+, ensure analyzer package,
 *                         proxy to `python -m analyzer <cmd> [args]`.
 *
 * Zero npm dependencies. Requires Python 3.10+ on PATH for analysis commands.
 */
const fs   = require("fs");
const os   = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT      = path.resolve(__dirname, "..");
const SKILL_DIR = path.join(ROOT, "skills", "ai-test-failure-analyzer");
const VERSION   = require(path.join(ROOT, "package.json")).version;
const HOME      = os.homedir();

const PASSTHROUGH = ["analyze", "serve-stdio", "serve-http", "preflight", "info", "tui", "web"];

const AGENTS = {
  claude:   { base: path.join(HOME, ".claude"),               kind: "dir",    dest: path.join(HOME, ".claude",  "skills", "ai-test-failure-analyzer") },
  codex:    { base: path.join(HOME, ".codex"),                kind: "dir",    dest: path.join(HOME, ".codex",   "skills", "ai-test-failure-analyzer") },
  opencode: { base: path.join(HOME, ".config", "opencode"),   kind: "dir",    dest: path.join(HOME, ".config",  "opencode", "skills", "ai-test-failure-analyzer") },
  cursor:   { base: path.join(HOME, ".cursor"),               kind: "file",   dest: path.join(HOME, ".cursor",  "rules", "ai-test-failure-analyzer.mdc") },
  gemini:   { base: path.join(HOME, ".gemini"),               kind: "append", dest: path.join(HOME, ".gemini",  "GEMINI.md") },
  windsurf: { base: path.join(HOME, ".codeium", "windsurf"), kind: "append", dest: path.join(HOME, ".codeium", "windsurf", "memories", "global_rules.md") },
};

function ensureDir(p) { fs.mkdirSync(p, { recursive: true }); }

function findPython() {
  for (const cmd of ["python3", "python"]) {
    const r = spawnSync(cmd, ["--version"], { encoding: "utf8" });
    if (r.status !== 0) continue;
    const ver = (r.stdout + r.stderr).trim();
    const m = ver.match(/Python (\d+)\.(\d+)/);
    if (m && (parseInt(m[1]) > 3 || (parseInt(m[1]) === 3 && parseInt(m[2]) >= 10))) {
      return cmd;
    }
  }
  return null;
}

function ensureAnalyzer(py) {
  const check = spawnSync(py, ["-c", "import analyzer"], { encoding: "utf8" });
  if (check.status === 0) return;
  console.log("ai-analyze: installing ai-test-failure-analyzer Python package...");
  const r = spawnSync(py, ["-m", "pip", "install", "ai-test-failure-analyzer", "--quiet"],
                      { stdio: "inherit" });
  if (r.status !== 0) {
    console.error("ai-analyze: pip install failed. Run: pip install ai-test-failure-analyzer");
    process.exit(1);
  }
}

function installAgent(name, opts) {
  const a = AGENTS[name];
  if (!opts.force && !fs.existsSync(a.base) && !opts.forceThis) {
    return { name, status: "skipped (not detected)" };
  }
  if (opts.dryRun) return { name, status: `would install -> ${a.dest}` };

  if (a.kind === "dir") {
    if (fs.existsSync(a.dest) && !opts.force) return { name, status: "exists (use --force)" };
    ensureDir(path.dirname(a.dest));
    fs.cpSync(SKILL_DIR, a.dest, { recursive: true });
    return { name, status: `installed -> ${a.dest}` };
  }
  if (a.kind === "file") {
    ensureDir(path.dirname(a.dest));
    fs.copyFileSync(path.join(SKILL_DIR, "SKILL.md"), a.dest);
    return { name, status: `installed -> ${a.dest}` };
  }
  // append — idempotent
  ensureDir(path.dirname(a.dest));
  const marker  = "<!-- ai-test-failure-analyzer -->";
  const pointer = `\n${marker}\nWhen asked to analyze test failures, follow the skill at ${SKILL_DIR}/SKILL.md.\n`;
  const cur = fs.existsSync(a.dest) ? fs.readFileSync(a.dest, "utf8") : "";
  if (cur.includes(marker)) return { name, status: "already referenced" };
  fs.writeFileSync(a.dest, cur + pointer);
  return { name, status: `pointer added -> ${a.dest}` };
}

function cmdInstall(argv) {
  const opts = { force: false, dryRun: false, only: null, skip: [] };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--force")    opts.force = true;
    if (argv[i] === "--dry-run")  opts.dryRun = true;
    if (argv[i] === "--only")  opts.only = (argv[++i] || "").split(",").filter(Boolean);
    if (argv[i] === "--skip")  opts.skip = (argv[++i] || "").split(",").filter(Boolean);
  }
  let names = Object.keys(AGENTS);
  if (opts.only) names = names.filter(n => opts.only.includes(n));
  names = names.filter(n => !opts.skip.includes(n));

  console.log(`ai-test-failure-analyzer v${VERSION} — installing skill (user-level)\n`);
  let any = false;
  for (const n of names) {
    const r = installAgent(n, { ...opts, forceThis: opts.only && opts.only.includes(n) });
    if (!r.status.startsWith("skipped")) any = true;
    console.log(`  ${n.padEnd(9)} ${r.status}`);
  }
  if (!any && !opts.only) {
    console.log("\n  No agents detected. Re-run with --only claude to force.");
  }
  console.log('\nDone. Ask your agent: "analyze test failures in playwright-report.json".');
  return 0;
}

function usage() {
  console.log(`ai-test-failure-analyzer v${VERSION} — root cause in seconds. Evidence, not intuition.

Usage:
  ai-analyze install [--only a,b] [--skip x] [--force] [--dry-run]
  ai-analyze <command> [args...]

Commands (require Python 3.10+):
  analyze       Run full 8-phase analysis on a test results file
  serve-stdio   Start MCP server over stdio (Claude Code / Cursor)
  serve-http    Start MCP server over HTTP (OpenAI / Gemini)
  info          Show version + supported frameworks

Examples:
  ai-analyze install
  ai-analyze analyze playwright-report.json
  ai-analyze analyze results.json --mode api-only
  ai-analyze serve-stdio
`);
}

function main() {
  const argv = process.argv.slice(2);
  const cmd  = argv[0];
  if (!cmd || cmd === "-h" || cmd === "--help")    { usage(); return 0; }
  if (cmd === "-v" || cmd === "--version")          { console.log(VERSION); return 0; }
  if (cmd === "install")                            return cmdInstall(argv.slice(1));

  if (PASSTHROUGH.includes(cmd)) {
    const py = findPython();
    if (!py) {
      console.error("ai-analyze: Python 3.10+ not found on PATH.\nInstall from https://python.org");
      return 1;
    }
    ensureAnalyzer(py);
    const r = spawnSync(py, ["-m", "analyzer", ...argv], {
      stdio: "inherit",
      env: { ...process.env, PYTHONUTF8: "1" },
    });
    return r.status === null ? 1 : r.status;
  }

  console.error(`ai-analyze: unknown command '${cmd}'. Run 'ai-analyze --help'.`);
  return 2;
}

process.exit(main());
