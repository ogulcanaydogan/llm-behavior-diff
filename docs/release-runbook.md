# Release Runbook

This runbook covers manual distribution and model-upgrade gating workflows.

## Prerequisites

- Repository default branch: `master`
- GitHub Actions enabled for the repository
- Package version updated in `pyproject.toml`
- Required secrets configured (see matrix below)
- Workflow runtime policy: Node24 deprecation closure is in place. Workflows
  keep `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` and use Node24-ready major
  action versions pinned by SHA.
- Workflow security policy: third-party actions are SHA-pinned. Dependabot
  auto-updates `github-actions` minor/patch versions weekly; major updates are
  handled in planned maintenance windows.

## Secrets and Permissions Matrix

| Workflow | Required Secrets | Required Permissions |
| --- | --- | --- |
| `publish-pypi.yml` | OIDC trusted publishing OR `TEST_PYPI_API_TOKEN` / `PYPI_API_TOKEN` fallback | `id-token: write`, `contents: read` |
| `docker-image.yml` | `GITHUB_TOKEN` (provided by Actions) | `packages: write`, `contents: read` |
| `model-upgrade-regression.yml` | `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` based on model ids; optional `EXPORT_CONNECTOR_API_KEY` for HTTP export dispatch; optional `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` for S3 export dispatch; optional Google ADC credential setup for GCS/BigQuery export dispatch; optional Azure identity credential setup for Azure Blob export dispatch; optional `SNOWFLAKE_PASSWORD` for Snowflake export dispatch; optional `REDSHIFT_PASSWORD` for Redshift export dispatch; optional `DATABRICKS_TOKEN` for Databricks export dispatch; optional `POSTGRES_PASSWORD` for PostgreSQL export dispatch; optional `CLICKHOUSE_DSN` for ClickHouse export dispatch (no extra secret needed for `factual_connector=wikipedia`) | `contents: read` |

## 1) Package Publish (Manual)

Workflow: `publish-pypi.yml`

Inputs:

- `target`: `testpypi` (default) or `pypi`
- `version_tag` (optional): for tag/version consistency check (example: `v1.0.0`)

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
- `gate_policy_pack` (optional, default `core`): `core|risk_averse|velocity`
- `gate_policy_file` (optional): repo-relative custom policy YAML path (takes precedence over pack)
- `factual_connector` (optional, default `none`): `none|wikipedia`
- `factual_connector_timeout` (optional, default `8`)
- `factual_connector_max_results` (optional, default `3`)
- `export_connector` (optional, default `none`): `none|http|s3|gcs|bigquery|snowflake|redshift|azure_blob|databricks|postgres|clickhouse|mssql|oracle|mysql`
- `export_connector_endpoint` (optional): required when `export_connector=http`
- `export_connector_timeout` (optional, default `10`)
- `export_s3_bucket` (optional): required when `export_connector=s3`
- `export_s3_prefix` (optional, default empty)
- `export_bq_project` (optional): required when `export_connector=bigquery`
- `export_bq_dataset` (optional): required when `export_connector=bigquery`
- `export_bq_table` (optional): required when `export_connector=bigquery`
- `export_bq_location` (optional)
- `export_sf_account` (optional): required when `export_connector=snowflake`
- `export_sf_user` (optional): required when `export_connector=snowflake`
- `export_sf_role` (optional)
- `export_sf_warehouse` (optional): required when `export_connector=snowflake`
- `export_sf_database` (optional): required when `export_connector=snowflake`
- `export_sf_schema` (optional): required when `export_connector=snowflake`
- `export_sf_table` (optional): required when `export_connector=snowflake`

GCS workflow wiring (env-based, no new workflow input):

- `EXPORT_GCS_BUCKET` repository variable is required when `export_connector=gcs`
- `EXPORT_GCS_PREFIX` repository variable is optional (default empty)
- `EXPORT_GCS_PROJECT` repository variable is optional (ADC project override)

Azure Blob workflow wiring (env-based, no new workflow input):

- `EXPORT_AZ_ACCOUNT_URL` repository variable is required when `export_connector=azure_blob`
- `EXPORT_AZ_CONTAINER` repository variable is required when `export_connector=azure_blob`
- `EXPORT_AZ_PREFIX` repository variable is optional (default empty)

Redshift workflow wiring (env-based, no new workflow input):

- `EXPORT_RS_HOST` repository variable is required when `export_connector=redshift`
- `EXPORT_RS_PORT` repository variable is optional (default `5439`)
- `EXPORT_RS_DATABASE` repository variable is required when `export_connector=redshift`
- `EXPORT_RS_USER` repository variable is required when `export_connector=redshift`
- `EXPORT_RS_SCHEMA` repository variable is required when `export_connector=redshift`
- `EXPORT_RS_TABLE` repository variable is required when `export_connector=redshift`
- `EXPORT_RS_SSLMODE` repository variable is optional (default `require`)
- `REDSHIFT_PASSWORD` secret is required when `export_connector=redshift`

Databricks workflow wiring (env-based, no new workflow input):

- `EXPORT_DBX_HOST` repository variable is required when `export_connector=databricks`
- `EXPORT_DBX_HTTP_PATH` repository variable is required when `export_connector=databricks`
- `EXPORT_DBX_CATALOG` repository variable is required when `export_connector=databricks`
- `EXPORT_DBX_SCHEMA` repository variable is required when `export_connector=databricks`
- `EXPORT_DBX_TABLE` repository variable is required when `export_connector=databricks`
- `DATABRICKS_TOKEN` secret is required when `export_connector=databricks`

PostgreSQL workflow wiring (env-based, no new workflow input):

- `EXPORT_PG_HOST` repository variable is required when `export_connector=postgres`
- `EXPORT_PG_PORT` repository variable is optional (default `5432`)
- `EXPORT_PG_DATABASE` repository variable is required when `export_connector=postgres`
- `EXPORT_PG_USER` repository variable is required when `export_connector=postgres`
- `EXPORT_PG_SCHEMA` repository variable is required when `export_connector=postgres`
- `EXPORT_PG_TABLE` repository variable is required when `export_connector=postgres`
- `EXPORT_PG_SSLMODE` repository variable is optional (default `require`)
- `POSTGRES_PASSWORD` secret is required when `export_connector=postgres`

ClickHouse workflow wiring (env-based, no new workflow input):

- `EXPORT_CH_DATABASE` repository variable is required when `export_connector=clickhouse`
- `EXPORT_CH_TABLE` repository variable is required when `export_connector=clickhouse`
- `CLICKHOUSE_DSN` secret is required when `export_connector=clickhouse` (mapped to `LLM_DIFF_EXPORT_CH_DSN`)

MSSQL workflow wiring (env-based, no new workflow input):

- `EXPORT_MS_HOST` repository variable is required when `export_connector=mssql`
- `EXPORT_MS_PORT` repository variable is optional (default `1433`)
- `EXPORT_MS_DATABASE` repository variable is required when `export_connector=mssql`
- `EXPORT_MS_USER` repository variable is required when `export_connector=mssql`
- `EXPORT_MS_SCHEMA` repository variable is required when `export_connector=mssql`
- `EXPORT_MS_TABLE` repository variable is required when `export_connector=mssql`
- `MSSQL_PASSWORD` secret is required when `export_connector=mssql`

Oracle workflow wiring (env-based, no new workflow input):

- `EXPORT_OR_HOST` repository variable is required when `export_connector=oracle`
- `EXPORT_OR_PORT` repository variable is optional (default `1521`)
- `EXPORT_OR_SERVICE_NAME` repository variable is required when `export_connector=oracle`
- `EXPORT_OR_USER` repository variable is required when `export_connector=oracle`
- `EXPORT_OR_SCHEMA` repository variable is required when `export_connector=oracle`
- `EXPORT_OR_TABLE` repository variable is required when `export_connector=oracle`
- `ORACLE_PASSWORD` secret is required when `export_connector=oracle`

MySQL workflow wiring (env-based, no new workflow input):

- `EXPORT_MYSQL_HOST` repository variable is required when `export_connector=mysql`
- `EXPORT_MYSQL_PORT` repository variable is optional (default `3306`)
- `EXPORT_MYSQL_DATABASE` repository variable is required when `export_connector=mysql`
- `EXPORT_MYSQL_USER` repository variable is required when `export_connector=mysql`
- `EXPORT_MYSQL_TABLE` repository variable is required when `export_connector=mysql`
- `MYSQL_PASSWORD` secret is required when `export_connector=mysql`

Default suite set when `suite_list` is empty:

- `suites/general_knowledge.yaml`
- `suites/instruction_following.yaml`
- `suites/safety_boundaries.yaml`
- `suites/coding_tasks.yaml`
- `suites/reasoning.yaml`

Gate policy:

- Workflow evaluates each suite report with selected policy.
- Policy resolution supports built-in packs (`core`, `risk_averse`, `velocity`) and optional custom YAML file (`version: v1`).
- When `gate_policy_file` is set, file-based policy overrides `gate_policy_pack`.
- Any suite-level policy fail causes workflow fail.
- Defaults to `strict + core` when no gate inputs are provided.

Core policy template:

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

Pack intent:

- `risk_averse`: tighter regression budgets and stricter critical-category max limits
- `velocity`: wider budgets while retaining safety/factual guardrails

Artifacts:

- Per-suite JSON reports are uploaded for audit/debug.
- Per-suite export artifacts are also uploaded:
  - `<suite>.csv` (metric-focused row export, no raw responses)
  - `<suite>.ndjson` (row-level full payload including responses/metadata)
  - `<suite>.junit.xml` (CI-friendly regression testcase mapping)
- Always-on benchmark artifacts are uploaded from report JSONs:
  - `benchmark.json` (machine-readable advisory summary)
  - `benchmark.md` (human-readable advisory summary appended to job summary)
- Benchmark output is advisory-only and does not override gate pass/fail.
- Benchmark summaries include extended significance signals (effect size + BH-FDR) when run-level significance metadata is available.
- Direct export dispatch applies transient retry (`max_attempts=3`, backoff `0.5s`, `1.0s` + bounded jitter) for network/service failures; validation/auth errors are not retried. Internally, all connectors use one shared registry-driven execution pipeline, and failure text includes connector/operation/attempt context.
- When `export_connector=http` is enabled, each generated export is also posted
  to the configured endpoint (`export_connector_endpoint`) via report command dispatch.
- When `export_connector=s3` is enabled, each generated export is also uploaded to
  the configured S3 bucket/prefix (`export_s3_bucket` / `export_s3_prefix`).
- When `export_connector=gcs` is enabled, each generated export is also uploaded to
  the configured GCS bucket/prefix (`EXPORT_GCS_BUCKET` / `EXPORT_GCS_PREFIX` repo vars)
  with optional ADC project override via `EXPORT_GCS_PROJECT`.
- When `export_connector=azure_blob` is enabled, each generated export is also uploaded to
  Azure Blob (`EXPORT_AZ_ACCOUNT_URL`, `EXPORT_AZ_CONTAINER`, optional `EXPORT_AZ_PREFIX`)
  using `DefaultAzureCredential`.
- Azure Blob export follows fail-fast semantics: missing config, authentication errors,
  or upload errors fail the command/workflow step.
- When `export_connector=bigquery` is enabled, only NDJSON exports are uploaded to
  BigQuery (`export_bq_project.export_bq_dataset.export_bq_table`), while CSV/JUnit
  artifacts are still generated and uploaded as workflow artifacts.
- BigQuery export follows fail-fast semantics: missing config, authentication errors,
  or row insert errors fail the command/workflow step.
- When `export_connector=snowflake` is enabled, only NDJSON exports are uploaded to
  Snowflake (`export_sf_database.export_sf_schema.export_sf_table`) with credentials
  from `--export-sf-password` or `LLM_DIFF_EXPORT_SF_PASSWORD` (workflow: `SNOWFLAKE_PASSWORD` secret).
- Snowflake export follows fail-fast semantics: missing config, authentication errors,
  or row insert errors fail the command/workflow step.
- When `export_connector=redshift` is enabled, only NDJSON exports are uploaded to
  Redshift (`export_rs_schema.export_rs_table`) using connection fields from repo vars and
  password from `--export-rs-password` or `LLM_DIFF_EXPORT_RS_PASSWORD` (workflow: `REDSHIFT_PASSWORD` secret).
- Redshift export follows fail-fast semantics: missing config, authentication errors,
  or row insert errors fail the command/workflow step.
- When `export_connector=databricks` is enabled, only NDJSON exports are uploaded to
  Databricks SQL (`export_dbx_catalog.export_dbx_schema.export_dbx_table`) using
  connection fields from repo vars and token from `--export-dbx-token` or
  `LLM_DIFF_EXPORT_DBX_TOKEN` (workflow: `DATABRICKS_TOKEN` secret).
- Databricks export follows fail-fast semantics: missing config, authentication errors,
  or row insert errors fail the command/workflow step.
- When `export_connector=postgres` is enabled, only NDJSON exports are uploaded to
  PostgreSQL (`export_pg_schema.export_pg_table`) using connection fields from repo vars
  and password from `--export-pg-password` or `LLM_DIFF_EXPORT_PG_PASSWORD`
  (workflow: `POSTGRES_PASSWORD` secret).
- PostgreSQL export follows fail-fast semantics: missing config, authentication errors,
  or row insert errors fail the command/workflow step.
- When `export_connector=clickhouse` is enabled, only NDJSON exports are uploaded to
  ClickHouse (`export_ch_database.export_ch_table`) using DSN from `--export-ch-dsn` or
  `LLM_DIFF_EXPORT_CH_DSN` (workflow: `CLICKHOUSE_DSN` secret).
- ClickHouse export follows fail-fast semantics: missing config, authentication errors,
  or row insert errors fail the command/workflow step.
- When `export_connector=mssql` is enabled, only NDJSON exports are uploaded to
  MSSQL (`export_ms_schema.export_ms_table`) using connection fields from repo vars and
  password from `--export-ms-password` or `LLM_DIFF_EXPORT_MS_PASSWORD`
  (workflow: `MSSQL_PASSWORD` secret).
- MSSQL export follows fail-fast semantics: missing config, authentication errors,
  or row insert errors fail the command/workflow step.
- When `export_connector=oracle` is enabled, only NDJSON exports are uploaded to
  Oracle (`export_or_schema.export_or_table`) using connection fields from repo vars and
  password from `--export-or-password` or `LLM_DIFF_EXPORT_OR_PASSWORD`
  (workflow: `ORACLE_PASSWORD` secret).
- Oracle export follows fail-fast semantics: missing config, authentication errors,
  or row insert errors fail the command/workflow step.
- When `export_connector=mysql` is enabled, only NDJSON exports are uploaded to
  MySQL (`export_mysql_database.export_mysql_table`) using connection fields from
  repo vars and password from `--export-mysql-password` or
  `LLM_DIFF_EXPORT_MYSQL_PASSWORD` (workflow: `MYSQL_PASSWORD` secret).
- MySQL export follows fail-fast semantics: missing config, authentication errors,
  or row insert errors fail the command/workflow step.
- When external factual connector is enabled, reports include metadata-only
  `factual_external` comparator payloads and run-level `factual_external_summary`.

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

## 5) Workflow Action Update Operations

- Dependabot opens weekly PRs for `.github/workflows/*` action updates.
- Dependabot policy ignores semver-major updates for `github-actions`.
- Review checklist for these PRs:
  - all `uses:` refs remain full 40-char commit SHAs
  - top-level workflow `permissions` remain least-privilege and unchanged unless intentional
  - `CI` and `Docker Image` checks stay green
- Major action version bumps are reviewed and merged only in separate planned
  hardening windows.
- Security drift guard tests in `tests/test_workflow_security_guard.py` and
  `tests/test_dependabot_policy_guard.py` enforce both rules.
