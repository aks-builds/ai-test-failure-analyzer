# Security Policy

## Reporting a Vulnerability

Report security issues via **GitHub Private Security Advisories** (do not open a public issue).

## Scope — we especially care about

- **Secret leakage**: captured output containing tokens, passwords, or keys reaching logs, reports, or GitHub issues
- **Path traversal**: a crafted test results path escaping the workspace root
- **Command injection**: hypothesis or evidence content being executed as shell

## Design guarantees

- **No shell=True**: all subprocess calls use explicit argument lists; user-controlled strings never reach a shell
- **Path traversal protection**: `safe_path()` resolves all paths relative to workspace root and rejects symlinks outside it
- **Size caps**: per-file (5 MB), per-scan (50 MB), per-log-line (4 KB), per-commit (200) — prevents OOM from adversarial inputs
- **Secrets redacted in config scans**: `.env` values matching token/secret/key/password patterns are masked in reports
- **No network calls from analysis**: the core analysis pipeline never makes outbound HTTP requests (GitHub issue creation is opt-in and explicit)

## Out of scope

- Vulnerabilities on already-compromised hosts
- Novel secret formats not covered by existing redaction patterns (human review is the backstop)
