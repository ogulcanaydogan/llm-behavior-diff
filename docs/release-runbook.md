# Release Runbook

This runbook covers manual distribution and model-upgrade gating workflows.

## Prerequisites

- Repository default branch: `master`
- GitHub Actions enabled for the repository
- Package version updated in `pyproject.toml`
- Required secrets configured (see matrix below)
- Workflow runtime policy: JavaScript-based actions are forced to Node24 via
  `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` at workflow scope.

## Secrets and Permissions Matrix

| Workflow | Required Secrets | Required Permissions |
| --- | --- | --- |
| `publish-pypi.yml` | OIDC trusted publishing OR `TEST_PYPI_API_TOKEN` / `PYPI_API_TOKEN` fallback | `id-token: write`, `contents: read` |
| `docker-image.yml` | `GITHUB_TOKEN` (provided by Actions) | `packages: write`, `contents: read` |
| `model-upgrade-regression.yml` | `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` based on model ids | `contents: read` |

## 1) Package Publish (Manual)

Workflow: `publish-pypi.yml`

Inputs:

- `target`: `testpypi` (default) or `pypi`
- `version_tag` (optional): for tag/version consistency check (example: `v0.1.0`)

Execution steps in workflow:

1. Build artifacts (`python -m build`)
2. Validate metadata (`twine check dist/*`)
3. Smoke install wheel and run `llm-diff --help`
4. Publish to selected target

Recommended sequence:

1. Run `target=testpypi`
2. Verify installation from TestPyPI
3. Run `target=pypi`

## 2) Docker Image Distribution

Workflow: `docker-image.yml`

Default behavior:

- On PR and `master` push: image build + smoke check only (`llm-diff --help`)

Manual release behavior (`workflow_dispatch`):

- `push_image=true` to push to GHCR
- Optional `version_tag` to publish semantic tag
- Optional `set_latest=true` to also push `latest`

Tagging rules:

- CI build tag: `sha-<shortsha>`
- Manual release tag: `<version_tag>` if provided, otherwise `sha-<shortsha>`

## 3) Model Upgrade Regression Gate

Workflow: `model-upgrade-regression.yml`

Triggers:

- Manual: `workflow_dispatch`
- Reusable: `workflow_call`

Inputs:

- `model_a` (baseline)
- `model_b` (candidate)
- `suite_list` (optional comma-separated override)
- `max_workers` (optional, default `4`)
- `gate_policy` (optional, default `strict`): `strict|balanced|permissive`

Default suite set when `suite_list` is empty:

- `suites/general_knowledge.yaml`
- `suites/instruction_following.yaml`
- `suites/safety_boundaries.yaml`
- `suites/coding_tasks.yaml`
- `suites/reasoning.yaml`

Gate policy:

- Workflow evaluates each suite report with selected policy.
- Any suite-level policy fail causes workflow fail.
- Defaults to `strict` when no `gate_policy` is provided.

Policy templates:

- `strict`: fail when `regressions > 0`
- `balanced`:
  - `allowed_regressions = max(1, floor(total_tests * 0.02))`
  - fail if regressions exceed allowed count
  - fail on any regression in `safety_boundary`, `hallucination_new`, `format_change`
- `permissive`:
  - `allowed_regressions = max(2, floor(total_tests * 0.05))`
  - fail if regressions exceed allowed count
  - fail when `hallucination_new > 0`
  - fail when `safety_boundary > 1`

Artifacts:

- Per-suite JSON reports are uploaded for audit/debug.

## 4) Local Pre-Flight Checklist

Use a project-local virtual environment (PEP 668-safe) and run:

```bash
make install-dev
make ci-local
```

Then run release-check parity locally:

```bash
make release-local
```

Equivalent explicit commands:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

ruff check src tests
black --check src tests
mypy src
pytest -q
.venv/bin/mkdocs build --strict
python -m build
twine check dist/*
```

Then validate installed CLI from wheel in a clean venv:

```bash
python -m venv .venv-smoke
. .venv-smoke/bin/activate
pip install --upgrade pip
pip install dist/*.whl
llm-diff --help
```
