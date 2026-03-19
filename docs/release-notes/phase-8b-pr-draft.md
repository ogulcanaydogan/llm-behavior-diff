# PR Draft — Phase 8B Stabilization

## Title
`Phase 8B stabilization: venv-first CI parity + docs truth-sync + release-readiness`

## What changed
- Stabilized core execution/reporting path and test suite around adapter expansion, optional judge, and extended significance reporting.
- Introduced venv-first local developer workflow and CI/release parity commands:
  - `make install-dev`
  - `make ci-local`
  - `make release-local`
- Completed docs/roadmap truth-sync to implemented state (bootstrap+Wilson run metadata, bootstrap delta CI + permutation p-value in compare).

## Why now
- Branch already contains the full stabilization surface; this PR packages it into review-friendly logical commits with reproducible local validation.
- Eliminates drift between current implementation, docs messaging, and local/CI execution pathways.

## Validation evidence
Executed locally on `.venv`:

```bash
make install-dev
make ci-local
make release-local
pytest -q tests/test_docs_consistency.py
```

Observed results:
- `ruff`, `black --check`, `mypy`, `pytest -q`, `mkdocs build --strict`: passed
- `python -m build`, `twine check dist/*`, wheel smoke `llm-diff --help`: passed
- docs consistency guard: passed

## Non-blocking warnings
- `setuptools` emits deprecation warnings for license metadata format during build.
- This does not block package build/check in current flow.

## Follow-ups
- Track packaging metadata modernization as a separate issue (SPDX/simple-string license metadata and related classifier cleanup).
