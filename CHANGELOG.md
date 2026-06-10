# Changelog

All notable changes to `ai-test-failure-analyzer` are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) / [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-06-14

### Added
- Evidence tier system (FULL_SOURCE vs API_ONLY mode, auto-detected from workspace)
- Noise filter: path block, keyword block, hypothesis deduplication, Tier-1 gate
- API-only mode for source-free workspaces (Newman, k6, public API testing)
- Newman (Postman CLI) JSON parser
- k6 load test summary JSON parser
- REST Assured error pattern recognition in JUnit fallback parser
- npm global CLI (`ai-analyze`) — zero npm deps, auto-installs Python package
- PyPI package renamed from `qa-test-failure-analyzer` to `ai-test-failure-analyzer`
- Claude Code skill installable via `/plugin install ai-test-failure-analyzer`
- Agent-agnostic skill install (`ai-analyze install`) for Claude, Cursor, Codex, Gemini, Windsurf
- Report mode banner (FULL_SOURCE / API_ONLY)
- "No application-layer fault" honest message when all hypotheses suppressed
- CI matrix expanded to Python 3.10, 3.11, 3.12 with aggregate `test` gate
- Release automation: dispatch → bump → PR → npm publish + PyPI publish + GitHub release
- CodeQL security scanning
- `--mode api-only` CLI flag to force API_ONLY analysis
