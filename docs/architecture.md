# Architecture

`llm-behavior-diff` follows a deterministic comparator-first pipeline.

## Runtime Flow

1. CLI parses command/options.
2. Runner loads and validates one suite YAML.
3. Provider resolver maps model ids to adapters:
   - `gpt-*`, `o1-*`, `o3-*` -> OpenAI
   - `claude-*` -> Anthropic
   - `litellm:<model_ref>` -> LiteLLM
   - `local:<model_ref>` -> Local OpenAI-compatible endpoint
4. For each test case:
   - model A/B calls run concurrently
   - retry + backoff + optional per-model rate-limit applied
5. Responses are sent to comparator pipeline:
   - semantic
   - factual
   - optional factual_external (`--factual-connector`, factual-applicable + semantic-diff tests only)
   - format
   - behavioral
   - optional judge (`--judge-model`, semantic-diff tests only)
6. Aggregator applies precedence:
   - semantic-same > factual > format > behavioral > unknown
7. BehaviorReport is assembled with diff stats, token usage, estimated cost, comparator summary,
   external factual summary, and run-level significance metadata (bootstrap + Wilson intervals).
   - judge/factual_external outputs are metadata-only and do not override deterministic final classification
8. Optional policy gate evaluates report artifacts with deterministic tiers
   (`strict`, `balanced`, `permissive`) plus pack resolution:
   - built-in packs: `core`, `risk_averse`, `velocity`
   - optional custom YAML policy file (`version: v1`, metadata-only config hook)
   - same resolution path used in CLI and CI workflow gate.
9. Optional benchmark summaries aggregate report artifacts into advisory-only quality signals.

## Core Modules

- `runner.py`: suite loading, execution orchestration, resilience controls
- `adapters/`: provider-specific model calls and metadata
- `comparators/`: deterministic scoring and decision outputs
- `aggregator.py`: final category/regression/improvement decision point
- `policy.py`: deterministic risk-tier gate evaluation, policy-pack resolution, custom YAML validation
- `benchmark.py`: artifact-first benchmark aggregation and fixed advisory quality pack
- `schema.py`: report/test/diff data models
- `cli.py`: command surface and formatting

## Error Handling Modes

- Default: fail-fast on first provider error.
- `--continue-on-error`: collect errors, continue other tests, report partial completion via metadata:
  - `processed_tests`
  - `failed_tests`
  - `errors`
- Judge errors are always non-fatal and are recorded as `judge_error`/`judge_uncertain` metadata decisions.
- External factual connector errors are non-fatal and recorded as `external_error` metadata decisions.

## Cost Tracking

- Per-model token usage is aggregated from adapter metadata.
- When `--judge-model` is enabled, judge token usage/cost is included in totals.
- Built-in pricing map is used unless overridden by `--pricing-file`.
- `pricing_source` indicates `builtin`, `file`, `builtin+file`, or `none`.
- `local` adapter reads `LLM_DIFF_LOCAL_BASE_URL` (default `http://localhost:11434/v1`)
  and optional `LLM_DIFF_LOCAL_API_KEY`.

## Reports

- Primary output is JSON from `run`.
- `report` renders table/json/html/markdown/csv/ndjson/junit views.
  - `csv` and `junit` stay metric/status focused and do not include raw responses.
  - `ndjson` includes raw responses and comparator metadata per diff row.
  - table/markdown include run-level bootstrap + Wilson CI when available.
  - optional direct connector dispatch (`--export-connector http|s3|gcs|bigquery|snowflake|redshift|azure_blob|databricks|postgres|clickhouse|mssql|oracle|mysql|mariadb`) posts rendered content externally.
  - connector dispatch is implemented through an internal connector registry with a single execution path (`resolve config -> validate -> prepare payload -> execute with retry`) to reduce connector drift.
  - `gcs` and `azure_blob` support all non-table formats (`azure_blob` via `DefaultAzureCredential`); `bigquery`, `snowflake`, `redshift`, `databricks`, `postgres`, `clickhouse`, `mssql`, `oracle`, `mysql`, and `mariadb` are NDJSON-only.
  - connector uploads are fail-fast when connector-specific validation/auth/upload fails.
- `compare` renders run-to-run metric deltas and optional markdown output.
- `compare` also computes bootstrap delta CI + permutation p-value + effect size (Cohen's h) + BH-FDR-adjusted significance from per-test outcomes when both reports include `diff_results`.
- `gate` evaluates one JSON report with selected tier + pack/file policy and returns CI-friendly exit codes.
- `benchmark` evaluates one or more JSON reports and returns advisory-only quality summaries (table/json/markdown), including extended significance summaries (effect size + BH-FDR) when run metadata supports it.
