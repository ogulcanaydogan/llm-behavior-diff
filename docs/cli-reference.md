# CLI Reference

`llm-diff` provides four commands:

- `run`: execute a suite against two models and write a JSON report
- `report`: render one JSON report in table/json/html/markdown/csv/ndjson/junit
- `compare`: compare two JSON reports and show metric deltas
- `gate`: evaluate one report against deterministic risk-tier policy templates

## Global

```bash
llm-diff --help
llm-diff --version
```

## `llm-diff run`

Run one suite file per command.

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite suites/general_knowledge.yaml \
  --output report.json
```

Options:

- `--model-a` (required): baseline model id
- `--model-b` (required): candidate model id
- `--suite` (required): suite YAML path
- `--output`, `-o`: output JSON path (default `llm_behavior_diff_report.json`)
- `--max-workers`: test-case parallelism (default `4`)
- `--dry-run`: validate suite only
- `--continue-on-error`: continue suite when a test fails
- `--max-retries`: transient call retry count (default `3`)
- `--rate-limit-rps`: per-model request rate limit, `0` disables it (default `0`)
- `--pricing-file`: optional YAML/JSON pricing override file
- `--judge-model`: optional LLM-as-judge model id (metadata-only, non-fatal, semantic-diff tests only)
- `--factual-connector`: `none` (default) or `wikipedia` (metadata-only, non-fatal, non-overriding)
- `--factual-connector-timeout`: per-request timeout in seconds (default `8.0`)
- `--factual-connector-max-results`: max connector evidence rows per test (default `3`)

Model id formats:

- Legacy resolver:
  - OpenAI: `gpt-*`, `o1-*`, `o3-*`
  - Anthropic: `claude-*`
- Explicit prefixes:
  - LiteLLM: `litellm:<model_ref>` (example: `litellm:openai/gpt-4o-mini`)
  - Local OpenAI-compatible: `local:<model_ref>` (example: `local:llama3.1`)

Local adapter environment variables:

- `LLM_DIFF_LOCAL_BASE_URL` (default: `http://localhost:11434/v1`)
- `LLM_DIFF_LOCAL_API_KEY` (optional; fallback placeholder is used when unset)

### Dry Run

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite suites/general_knowledge.yaml \
  --dry-run
```

## `llm-diff report`

Render a single run report.

```bash
llm-diff report report.json --format table
llm-diff report report.json --format markdown -o report.md
llm-diff report report.json --format html -o report.html
llm-diff report report.json --format csv -o report.csv
llm-diff report report.json --format ndjson -o report.ndjson
llm-diff report report.json --format junit -o report.junit.xml
llm-diff report report.json --format csv -o report.csv \
  --export-connector http --export-endpoint https://example.com/ingest
llm-diff report report.json --format ndjson -o report.ndjson \
  --export-connector s3 --export-s3-bucket my-bucket \
  --export-s3-prefix team-a/exports --export-s3-region eu-west-1
llm-diff report report.json --format markdown -o report.md \
  --export-connector gcs --export-gcs-bucket my-bucket \
  --export-gcs-prefix team-a/exports --export-gcs-project analytics-prj
llm-diff report report.json --format ndjson -o report.ndjson \
  --export-connector bigquery \
  --export-bq-project analytics-prj \
  --export-bq-dataset llm_diff \
  --export-bq-table diff_rows \
  --export-bq-location EU
llm-diff report report.json --format ndjson -o report.ndjson \
  --export-connector snowflake \
  --export-sf-account xy12345.eu-west-1 \
  --export-sf-user svc_llm_diff \
  --export-sf-warehouse COMPUTE_WH \
  --export-sf-database ANALYTICS_DB \
  --export-sf-schema LLM_DIFF \
  --export-sf-table DIFF_ROWS
```

Options:

- `report_file` (required): JSON report path
- `--format`: `table` (default), `json`, `html`, `markdown`, `csv`, `ndjson`, `junit`
- `--output`, `-o`: output file path (stdout when omitted)
- `--export-connector`: `none` (default), `http`, `s3`, `gcs`, `bigquery`, or `snowflake`
- `--export-endpoint`: required when `--export-connector=http`
- `--export-timeout`: connector timeout seconds (default `10.0`)
- `--export-api-key`: optional explicit API key (fallback: `LLM_DIFF_EXPORT_API_KEY`)
- `--export-s3-bucket`: required when `--export-connector=s3`
- `--export-s3-prefix`: optional S3 key prefix (default empty)
- `--export-s3-region`: optional S3 region override
- `--export-gcs-bucket`: required when `--export-connector=gcs`
- `--export-gcs-prefix`: optional GCS object prefix (default empty)
- `--export-gcs-project`: optional GCS project override (ADC project used when omitted)
- `--export-bq-project`: required when `--export-connector=bigquery`
- `--export-bq-dataset`: required when `--export-connector=bigquery`
- `--export-bq-table`: required when `--export-connector=bigquery`
- `--export-bq-location`: optional BigQuery location override
- `--export-sf-account`: required when `--export-connector=snowflake`
- `--export-sf-user`: required when `--export-connector=snowflake`
- `--export-sf-password`: optional explicit Snowflake password (fallback: `LLM_DIFF_EXPORT_SF_PASSWORD`)
- `--export-sf-role`: optional Snowflake role
- `--export-sf-warehouse`: required when `--export-connector=snowflake`
- `--export-sf-database`: required when `--export-connector=snowflake`
- `--export-sf-schema`: required when `--export-connector=snowflake`
- `--export-sf-table`: required when `--export-connector=snowflake`

`report` table/markdown output includes run-level bootstrap + Wilson confidence intervals when
`metadata.significance` is present.

`report --format html` generates a self-contained interactive explorer (no external JS/CSS/CDN),
including KPI cards, category breakdown, filterable/sortable diff table, and expandable row details.

Export format behavior:

- `csv`: one row per `diff_result`, metric-focused columns, no raw model responses.
- `ndjson`: one JSON object per `diff_result`, includes run context + comparator metadata + raw responses.
- `junit`: one `<testcase>` per `diff_result`; `is_regression=true` maps to `<failure>`, others pass with status in `system-out`.
- direct connector dispatch is opt-in and supports `http`, `s3`, `gcs`, `bigquery`, and `snowflake`.
- connector dispatch requires non-`table` formats.
- `gcs` supports all non-`table` report formats and uses ADC credentials.
- `bigquery` dispatch requires `--format ndjson` and fails fast on insert errors.
- `snowflake` dispatch requires `--format ndjson` and fails fast on insert errors.

## `llm-diff compare`

Compare two report files.

```bash
llm-diff compare before.json after.json
llm-diff compare before.json after.json -o comparison.md
```

Options:

- `result_a` (required): run A JSON
- `result_b` (required): run B JSON
- `--output`, `-o`: optional markdown summary output path

`compare` computes bootstrap delta CI + permutation p-values on-the-fly from `diff_results`
when both reports include non-empty test-level outcomes.

## `llm-diff gate`

Evaluate one run report with a deterministic gate policy.

```bash
llm-diff gate report.json --policy strict
llm-diff gate report.json --policy balanced --format json -o gate.json
llm-diff gate report.json --policy balanced --policy-pack risk_averse
llm-diff gate report.json --policy strict --policy-file custom-policy.yaml
```

Options:

- `report_file` (required): JSON report path
- `--policy`: `strict` (default), `balanced`, `permissive`
- `--policy-pack`: `core` (default), `risk_averse`, `velocity`
- `--policy-file`: optional custom YAML policy file; takes precedence over `--policy-pack`
- `--format`: `table` (default) or `json`
- `--output`, `-o`: optional output file path

Built-in policy packs:

- `core`: preserves existing gate semantics
  - `strict`: fail when `regressions > 0`
  - `balanced`:
    - `allowed_regressions = max(1, floor(total_tests * 0.02))`
    - fail on any regression in `safety_boundary`, `hallucination_new`, `format_change`
  - `permissive`:
    - `allowed_regressions = max(2, floor(total_tests * 0.05))`
    - fail when `hallucination_new > 0`
    - fail when `safety_boundary > 1`
- `risk_averse`: tighter budgets and stricter category guardrails
- `velocity`: wider regression budgets with safety/factual guardrails retained

Custom policy file schema (YAML, `version: v1`):

```yaml
version: v1
name: custom_pack_name
tiers:
  strict:
    allowed_regressions:
      type: absolute
      value: 0
    critical_category_max: {}
  balanced:
    allowed_regressions:
      type: percent_floor
      percent: 0.02
      floor: 1
    critical_category_max:
      safety_boundary: 0
  permissive:
    allowed_regressions:
      type: percent_floor
      percent: 0.05
      floor: 2
    critical_category_max: {}
```

- `allowed_regressions.type` supports `absolute` and `percent_floor`.
- Unknown tiers/categories or invalid numeric ranges fail fast with validation errors.
- Gate JSON output includes `policy_pack` and `policy_source` for traceability.

## Exit Behavior

- Invalid input/suite/report parsing returns non-zero exit.
- `run` fail-fast is default; set `--continue-on-error` for partial progress mode.
- `--judge-model` never overrides deterministic final category/regression flags; it only adds metadata.
- `--factual-connector` never overrides deterministic final category/regression flags; it only adds metadata.
- `compare` includes cost delta row only when both reports include cost metadata.
- `compare` includes significance rows only when both reports include non-empty `diff_results`.
- `gate` exits with:
  - `0`: pass
  - `2`: policy fail
  - `1`: usage/parse/runtime error
