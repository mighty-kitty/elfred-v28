# GitHub Release Checklist

This directory is a clean release candidate for sharing EMOS as a local memory
service that another personal-agent project can call through the API.

## Included

- `src/`: memory-system source code.
- `configs/`: retrieval and runtime configuration defaults.
- `docs/`: receiver-facing API, deployment, handoff, and operations guides.
- `examples/`: minimal API client and request collection.
- `scripts/`: local operator and demo entrypoints.
- `tests/`: regression and contract tests.
- `data/benchmarks/`: small benchmark fixtures required by the test suite.
- `.env.example`: environment-variable template with placeholders only.
- `.github/workflows/tests.yml`: Windows Python 3.10 pytest workflow.

## Excluded

- Runtime memory stores, logs, delivery packs, temp files, caches, and local
  model directories.
- Paper artifacts and manuscript directories.
- Zip, PDF, SQLite runtime files, and Python bytecode.
- Any local API key value or secret value.

## Pre-Push Checks

Run these from the release-candidate root:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
rg -n '[A-Z]:\\\\' README.md docs examples scripts configs src tests .github GITHUB_RELEASE_CHECKLIST.md
rg -l -P '(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}' README.md docs src tests configs examples scripts .env.example GITHUB_RELEASE_CHECKLIST.md .github
```

Expected result: tests pass, no absolute local path references, and zero
strict OpenAI-like secret hits.

## Upload

```powershell
git init
git add .
git commit -m "Initial EMOS memory service release candidate"
git branch -M main
git remote add origin <repo-url>
git push -u origin main
```
