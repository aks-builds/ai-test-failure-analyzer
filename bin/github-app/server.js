#!/usr/bin/env node
/**
 * GitHub App — listens for check_run.completed webhooks,
 * downloads test result artifacts, runs ai-analyze, posts PR comment.
 *
 * Required env vars:
 *   GITHUB_APP_ID, GITHUB_PRIVATE_KEY, GITHUB_WEBHOOK_SECRET
 *   PORT (default: 3000)
 */
"use strict";

const http = require("http");
const { createHmac, timingSafeEqual } = require("crypto");
const { execFileSync } = require("child_process");
const https = require("https");
const os = require("os");
const path = require("path");
const fs = require("fs");

const PORT = parseInt(process.env.PORT || "3000", 10);
const WEBHOOK_SECRET = process.env.GITHUB_WEBHOOK_SECRET || "";

if (!WEBHOOK_SECRET) {
  console.error("[ERROR] GITHUB_WEBHOOK_SECRET is not set. All webhook requests will be rejected.");
}

function verifySignature(body, signature) {
  if (!WEBHOOK_SECRET) return false;
  const expected = "sha256=" + createHmac("sha256", WEBHOOK_SECRET).update(body).digest("hex");
  if (expected.length !== signature.length) return false;
  return timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}

function downloadArtifact(url, token, dest) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, {
      headers: { Authorization: `Bearer ${token}`, "User-Agent": "ai-analyze-app/2.0" },
    }, (res) => {
      if (res.statusCode === 302 || res.statusCode === 301) {
        return downloadArtifact(res.headers.location, token, dest).then(resolve).catch(reject);
      }
      const out = fs.createWriteStream(dest);
      res.pipe(out);
      out.on("finish", resolve);
      out.on("error", reject);
    });
    req.on("error", reject);
  });
}

async function handleCheckRun(payload, token) {
  const { check_run, repository } = payload;
  if (check_run.conclusion !== "failure") return;

  // Find artifact named 'test-results' or '*results*'
  const artifactsUrl = `https://api.github.com/repos/${repository.full_name}/actions/runs/${check_run.details_url?.match(/runs\/(\d+)/)?.[1]}/artifacts`;
  // Simplified: log and skip if we can't parse the run ID
  const runId = check_run.details_url?.match(/runs\/(\d+)/)?.[1];
  if (!runId) return;

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "atfa-"));
  const zipPath = path.join(tmpDir, "artifact.zip");
  let extractDir = null;

  try {
    // Download artifacts list
    const artifactsResp = await new Promise((resolve, reject) => {
      https.get(artifactsUrl, {
        headers: { Authorization: `Bearer ${token}`, "User-Agent": "ai-analyze-app/2.0",
                   Accept: "application/vnd.github+json" },
      }, (res) => {
        let data = "";
        res.on("data", d => data += d);
        res.on("end", () => { try { resolve(JSON.parse(data)); } catch (e) { reject(e); } });
      }).on("error", reject);
    });

    const artifact = (artifactsResp.artifacts || []).find(a =>
      a.name.includes("result") || a.name.includes("test")
    );
    if (!artifact) return;

    // GitHub returns a zip archive — download to zipPath then extract
    await downloadArtifact(artifact.archive_download_url, token, zipPath);

    extractDir = fs.mkdtempSync(path.join(os.tmpdir(), "atfa-extract-"));
    try {
      execFileSync("unzip", ["-q", zipPath, "-d", extractDir]);
    } catch (e) {
      console.error("Artifact extraction failed:", e.message);
      return;
    }

    // Find the first supported result file in the extracted directory
    const extractedFiles = fs.readdirSync(extractDir);
    const resultFile = extractedFiles.find(f =>
      f.endsWith(".json") || f.endsWith(".xml") || f.endsWith(".trx")
    );
    if (!resultFile) {
      console.error("No supported result file found in artifact zip");
      return;
    }
    const artifactPath = path.join(extractDir, resultFile);

    // Run analysis
    const analysisJson = execFileSync("ai-analyze", ["analyze", artifactPath, "--format", "json"], {
      timeout: 120000, encoding: "utf8",
    });
    const analysis = JSON.parse(analysisJson);
    const topHyp = analysis.hypotheses?.[0];
    if (!topHyp) return;

    const comment = [
      "## 🩻 Test Failure Analysis",
      "",
      `**Root Cause [${topHyp.confidence}%]:** ${topHyp.title}`,
      "",
      topHyp.summary,
      "",
      "**Remediation:**",
      ...(topHyp.remediation || []).map(r => `- ${r}`),
      ...(topHyp.buggy_location ? [`\n**Location:** \`${topHyp.buggy_location}\``] : []),
      "",
      "_Powered by [ai-test-failure-analyzer](https://github.com/aks-builds/ai-test-failure-analyzer)_",
    ].join("\n");

    // Post PR comment via Octokit (simplified — use REST directly)
    const prNumber = check_run.pull_requests?.[0]?.number;
    if (!prNumber) return;

    const commentBody = JSON.stringify({ body: comment });
    await new Promise((resolve, reject) => {
      const req = https.request({
        hostname: "api.github.com",
        path: `/repos/${repository.full_name}/issues/${prNumber}/comments`,
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(commentBody),
          "User-Agent": "ai-analyze-app/2.0",
          Accept: "application/vnd.github+json",
        },
      }, resolve);
      req.on("error", reject);
      req.write(commentBody);
      req.end();
    });
  } finally {
    try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch {}
    if (extractDir) {
      try { fs.rmSync(extractDir, { recursive: true, force: true }); } catch {}
    }
  }
}

const server = http.createServer(async (req, res) => {
  if (req.method !== "POST" || req.url !== "/webhook") {
    res.writeHead(404);
    res.end("Not found");
    return;
  }

  const MAX_BODY = 1_048_576; // 1 MB
  let body = "";
  let requestAborted = false;
  req.on("data", chunk => {
    body += chunk;
    if (body.length > MAX_BODY) {
      requestAborted = true;
      res.writeHead(413, { "Content-Type": "text/plain" });
      res.end("Payload Too Large");
      req.destroy();
    }
  });
  req.on("end", async () => {
    if (requestAborted) return;
    const sig = req.headers["x-hub-signature-256"] || "";
    if (!verifySignature(body, sig)) {
      res.writeHead(401);
      res.end("Invalid signature");
      return;
    }
    res.writeHead(200);
    res.end("OK");

    try {
      const payload = JSON.parse(body);
      const event = req.headers["x-github-event"];
      const token = process.env.GITHUB_TOKEN || "";
      if (event === "check_run" && payload.action === "completed") {
        await handleCheckRun(payload, token);
      }
    } catch (err) {
      console.error("Webhook handler error:", err.message);
    }
  });
});

server.listen(PORT, () => {
  console.log(`ai-analyze GitHub App listening on port ${PORT}`);
});
