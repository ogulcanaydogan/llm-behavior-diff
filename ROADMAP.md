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
- [x] GitHub Actions CI
- [x] Docker image
- [x] PyPI packaging (`pip install llm-behavior-diff`)

## Phase 5: Documentation & Launch
- [x] Professional README
- [x] mkdocs site
- [x] Launch post for dev.to / HN

## Remaining Planned Items
No open roadmap items at this time. Future work will be tracked as new phases.

## Success Metrics
- Can compare any two LLM versions in under 30 minutes for 100 test cases
- Reports highlight top 10 behavioral regressions/improvements with 95%+ accuracy
- Used in production by at least 3 organizations within 6 months
- <5% false positive rate on behavioral diff detection
