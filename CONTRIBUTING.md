# Contributing

## Dev setup

```bash
git clone https://github.com/aks-builds/ai-test-failure-analyzer
cd ai-test-failure-analyzer
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
npm install  # only needed to run npm test
```

## Running tests

```bash
pytest tests/analyzer -q       # Python unit tests
npm test                       # Node CLI smoke tests
```

## Making a change

1. Branch from `main`: `git checkout -b feat/short-description`
2. Write a failing test first (TDD)
3. Implement the minimal code to pass it
4. Commit with [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `chore:`
5. Open a PR against `main` — CI must pass

## Good contributions

- New framework parsers (Artillery, Gatling, Insomnia CLI, WebdriverIO native)
- New noise keyword patterns
- API-only hypothesis templates for additional HTTP patterns
- Cross-platform fixes

## Releasing (maintainers only)

1. Go to **Actions → release → Run workflow**, pick bump (`patch` / `minor` / `major`)
2. Workflow opens a `release/vX.Y.Z` PR with auto-merge enabled
3. Once CI passes, the PR merges and `publish.yml` ships to npm + PyPI + GitHub release

Required secrets: `NPM_TOKEN`, `PYPI_TOKEN`, `RELEASE_PR_PAT`
