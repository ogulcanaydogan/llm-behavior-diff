# ROADMAP — llm-behavior-diff

## Vision
The `git diff` for LLM behavior. When you upgrade a model version, know exactly what changed — not just outputs, but reasoning patterns, safety boundaries, factual accuracy, and instruction following. Essential for enterprise MLOps.

## Phase 1: Core Diff Engine (Week 1)
- [x] Set up Python project with pyproject.toml (src/llm_behavior_diff/)
  - Python 3.11+, deps: click, rich, pydantic, openai, anthropic, litellm, numpy, sentence-transformers
  - AC: `pip install -e .` works
- [x] Define test case schema (src/llm_behavior_diff/schema.py)
  - TestCase: prompt, expected_behavior (not exact match — behavioral), category, tags
  - TestSuite: collection of TestCases with metadata
  - DiffResult: per-test comparison result
  - BehaviorReport: aggregated diff report
  - AC: Schema validates sample test suites
- [x] Build model adapter layer (src/llm_behavior_diff/adapters/)
  - adapters/openai_adapter.py — OpenAI API (GPT-4o, GPT-4.5, etc.)
  - adapters/anthropic_adapter.py — Anthropic API (Claude models)
  - adapters/litellm_adapter.py — LiteLLM provider routing
  - adapters/local_adapter.py — Local OpenAI-compatible endpoint
  - adapters/base.py — Abstract ModelAdapter with generate() method
  - AC: Can query at least 2 different providers
- [x] Implement test runner (src/llm_behavior_diff/runner.py)
  - Run test suite against two model versions concurrently
  - Rate limiting, retry logic, cost tracking
  - Progress bar and rich terminal UX are implemented
  - AC: Can run 50 test cases against 2 models in parallel

## Phase 1.5: Hardening (Completed)
- [x] Add transient retry wrapper (exponential backoff + jitter)
- [x] Add per-model rate limiter (`--rate-limit-rps`)
- [x] Add cost metadata (`token_usage`, `estimated_cost_usd`, `pricing_source`)
- [x] Add partial-failure mode (`--continue-on-error`) with error summaries
- [x] Add pricing override support (`--pricing-file`)
- [x] Extend compare output with cost deltas when available

## Phase 2: Comparator-First Deterministic V1 (Week 1-2)
- [x] Build semantic comparator (src/llm_behavior_diff/comparators/semantic.py)
  - Sentence embedding similarity (sentence-transformers)
  - Semantic similarity threshold for "same" vs "different"
  - AC: Correctly identifies semantically equivalent but differently worded outputs
- [x] Build behavioral comparator (src/llm_behavior_diff/comparators/behavioral.py)
  - Deterministic expected-behavior coverage deltas
  - Thresholds: `>= +0.20` improvement, `<= -0.20` regression
  - AC: Deterministic improvement/regression/no-change decisions
- [x] Build factual comparator (src/llm_behavior_diff/comparators/factual.py)
  - Applies on factual/current/history weighted tests only
  - Detects `hallucination_new`, `hallucination_fixed`, `knowledge_change`
  - AC: Deterministic factual drift detection without external APIs
- [x] Build format comparator (src/llm_behavior_diff/comparators/format.py)
  - Checks JSON/table/exact-count/yes-no structural constraints
  - AC: Deterministic format/instruction compliance drift detection
- [x] Implement diff aggregator (src/llm_behavior_diff/aggregator.py)
  - Precedence: semantic-same > factual > format > behavioral > unknown
  - Writes comparator breakdowns into metadata
  - AC: Produces deterministic final categories and run-level summaries

## Phase 6: Post-Phase-2 Enhancements (Completed)
- [x] LLM-as-judge comparator mode (optional, metadata-only, non-fatal)
- [x] Statistical significance layer / confidence interval reporting (bootstrap CI)

## Phase 3: Reporting & CLI (Week 2)
- [x] Build report generator (baseline in CLI formatters)
  - JSON detailed report
  - HTML interactive report with side-by-side comparisons
  - Markdown summary for PR comments
  - Terminal rich output
  - AC: Advanced visual/report explorer enhancements shipped
- [x] Build CLI (src/llm_behavior_diff/cli.py)
  - `llm-diff run --model-a gpt-4o --model-b gpt-4.5 --suite tests.yaml`
  - `llm-diff report <results.json> --format html`
  - `llm-diff compare <result-a.json> <result-b.json>` — compare two runs
  - AC: All commands work
- [x] Build test suite templates (suites/)
  - suites/general_knowledge.yaml
  - suites/instruction_following.yaml
  - suites/safety_boundaries.yaml
  - suites/coding_tasks.yaml
  - suites/reasoning.yaml
  - AC: At least 10 test cases per suite
- [x] Write tests (tests/)
  - AC: >80% coverage

## Phase 4: CI/CD & Distribution
- [x] GitHub Action for model upgrade regression testing
- [x] Risk-tier release-policy templates (strict/balanced/permissive)
- [x] GitHub Actions CI
- [x] Node24 Actions deprecation closure (workflow force flag + Node24-ready major action window)
- [x] CI security hardening (SHA-pinned actions + permission baseline + Dependabot actions updates, with auto major bumps disabled)
- [x] Docker image
- [x] PyPI packaging (`pip install llm-behavior-diff`)

## Phase 5: Documentation & Launch
- [x] Professional README
- [x] mkdocs site
- [x] Launch post for dev.to / HN

## Phase 10: Policy Extensibility (Completed)
- [x] Policy packs for deterministic gate engine (`core`, `risk_averse`, `velocity`)
- [x] Custom YAML policy hook (`version: v1`) with strict validation
- [x] CLI + model-upgrade workflow parity for pack/file policy resolution

## Phase 11: Enterprise Reporting / Export Integrations (Completed)
- [x] Artifact-first enterprise export formats in `report` command (`csv`, `ndjson`, `junit`)
- [x] Model-upgrade workflow parity: per-suite JSON + export artifacts upload
- [x] Docs truth-sync for export behavior and artifact contracts
- [x] Optional direct export connector (`http`) for report command + workflow parity
- [x] Provider-specific external sink V1 (`s3`) for report command + workflow parity
- [x] Provider-specific external sink V2 (`bigquery`, NDJSON-only) for report command + workflow parity
- [x] Provider-specific external sink V3 (`snowflake`, NDJSON-only) for report command + workflow parity
- [x] Provider-specific external sink V4 (`gcs`, all non-table formats) for report command + workflow parity
- [x] Provider-specific external sink V5 (`redshift`, NDJSON-only) for report command + workflow parity
- [x] Provider-specific external sink V6 (`azure_blob`, all non-table formats) for report command + workflow parity
- [x] Provider-specific external sink V7 (`databricks`, NDJSON-only) for report command + workflow parity
- [x] Provider-specific external sink V8 (`postgres`, NDJSON-only) for report command + workflow parity
- [x] Provider-specific external sink V9 (`clickhouse`, NDJSON-only) for report command + workflow parity
- [x] Provider-specific external sink V10 (`mssql`, NDJSON-only) for report command + workflow parity
- [x] Provider-specific external sink V11 (`oracle`, NDJSON-only) for report command + workflow parity
- [x] Provider-specific external sink V12 (`mysql`, NDJSON-only) for report command + workflow parity
- [x] Provider-specific external sink V13 (`mariadb`, NDJSON-only) for report command + workflow parity

## Phase 14: Benchmark Quality Pack (Completed)
- [x] Artifact-first `benchmark` command for report JSON aggregation
- [x] Fixed advisory quality checks (failed tests, critical regressions, unknown-rate, runtime outliers)
- [x] Model-upgrade workflow parity with always-on benchmark artifact outputs

## Phase 14C: Extended Statistics V2 (Completed)
- [x] Compare output extended with effect size (Cohen's h) + BH-FDR-adjusted significance
- [x] Benchmark summary extended with suite-level effect size/FDR metadata and advisory signal
- [x] Metadata/output-only contract preserved (no gate semantic override)

## Phase 15: Export Connector Reliability Hardening (Completed)
- [x] Reliability V1: transient retry wrapper + attempt-context failure diagnostics (fail-fast preserved)
- [x] Reliability V2: internal connector registry + shared validation/execution flow + contract matrix tests

## Current Status
No open committed roadmap items at this time. GA baseline is `v1.0.0`; future exploration is tracked as non-committed candidates and promoted into new phases only when prioritized.

## Success Metrics
- Can compare any two LLM versions in under 30 minutes for 100 test cases
- Reports highlight top 10 behavioral regressions/improvements with 95%+ accuracy
- Used in production by at least 3 organizations within 6 months
- <5% false positive rate on behavioral diff detection
