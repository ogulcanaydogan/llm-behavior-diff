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
   - format
   - behavioral
   - optional judge (`--judge-model`, semantic-diff tests only)
6. Aggregator applies precedence:
   - semantic-same > factual > format > behavioral > unknown
7. BehaviorReport is assembled with diff stats, token usage, estimated cost, comparator summary,
   and run-level significance metadata (bootstrap + Wilson intervals).
   - judge output is metadata-only and does not override deterministic final classification

## Core Modules

- `runner.py`: suite loading, execution orchestration, resilience controls
- `adapters/`: provider-specific model calls and metadata
- `comparators/`: deterministic scoring and decision outputs
- `aggregator.py`: final category/regression/improvement decision point
- `schema.py`: report/test/diff data models
- `cli.py`: command surface and formatting

## Error Handling Modes

- Default: fail-fast on first provider error.
- `--continue-on-error`: collect errors, continue other tests, report partial completion via metadata:
  - `processed_tests`
  - `failed_tests`
  - `errors`
- Judge errors are always non-fatal and are recorded as `judge_error`/`judge_uncertain` metadata decisions.

## Cost Tracking

- Per-model token usage is aggregated from adapter metadata.
- When `--judge-model` is enabled, judge token usage/cost is included in totals.
- Built-in pricing map is used unless overridden by `--pricing-file`.
- `pricing_source` indicates `builtin`, `file`, `builtin+file`, or `none`.
- `local` adapter reads `LLM_DIFF_LOCAL_BASE_URL` (default `http://localhost:11434/v1`)
  and optional `LLM_DIFF_LOCAL_API_KEY`.

## Reports

- Primary output is JSON from `run`.
- `report` renders table/json/html/markdown views (table/markdown include run-level bootstrap + Wilson CI when available).
- `compare` renders run-to-run metric deltas and optional markdown output.
- `compare` also computes bootstrap delta CI + permutation p-value from per-test outcomes when both reports include `diff_results`.
