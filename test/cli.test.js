// test/cli.test.js
"use strict";
const { spawnSync } = require("child_process");
const path = require("path");
const assert = require("assert");
const pkg = require("../package.json");

const CLI = path.join(__dirname, "..", "bin", "cli.js");
function run(...args) {
  return spawnSync(process.execPath, [CLI, ...args], { encoding: "utf8", timeout: 10_000 });
}

// --version
{
  const r = run("--version");
  assert.strictEqual(r.status, 0, `--version exited ${r.status}: ${r.stderr}`);
  assert.ok(r.stdout.includes(pkg.version), `stdout should contain ${pkg.version}, got: ${r.stdout}`);
  console.log("✓ --version");
}

// --help
{
  const r = run("--help");
  assert.strictEqual(r.status, 0, `--help exited ${r.status}: ${r.stderr}`);
  assert.ok(r.stdout.includes("ai-analyze") || r.stdout.includes("ai-test-failure-analyzer"), "help should mention tool name");
  console.log("✓ --help");
}

// install --dry-run (does not need Python)
{
  const r = run("install", "--dry-run");
  assert.strictEqual(r.status, 0, `install --dry-run exited ${r.status}: ${r.stderr}`);
  const combined = r.stdout + r.stderr;
  assert.ok(combined.includes("would install") || combined.includes("skipped"), `dry run should show intent, got: ${combined}`);
  console.log("✓ install --dry-run");
}

// unknown command exits 2
{
  const r = run("not-a-real-command");
  assert.strictEqual(r.status, 2, `unknown command should exit 2, got ${r.status}`);
  console.log("✓ unknown command exits 2");
}

console.log(`\nAll CLI tests passed (ai-test-failure-analyzer v${pkg.version}).`);
