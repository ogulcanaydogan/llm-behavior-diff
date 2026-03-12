# ROADMAP — llm-behavior-diff

## Vision
The `git diff` for LLM behavior. When you upgrade a model version, know exactly what changed — not just outputs, but reasoning patterns, safety boundaries, factual accuracy, and instruction following. Essential for enterprise MLOps.

## Phase 1: Core Diff Engine (Week 1)
- [ ] Set up Python project with pyproject.toml (src/llm_behavior_diff/)
  - Python 3.11+, deps: click, rich, pydantic, openai, anthropic, litellm, numpy, sentence-transformers
  - AC: `pip install -e .` works
- [ ] Define test case schema (src/llm_behavior_diff/schema.py)
  - TestCase: prompt, expected_behavior (not exact match — behavioral), category, tags
  - TestSuite: collection of TestCases with metadata
  - DiffResult: per-test comparison result
  - BehaviorReport: aggregated diff report
  - AC: Schema validates sample test suites
- [ ] Build model adapter layer (src/llm_behavior_diff/adapters/)
  - adapters/openai_adapter.py — OpenAI API (GPT-4o, GPT-4.5, etc.)
  - adapters/anthropic_adapter.py — Anthropic API (Claude models)
  - adapters/litellm_adapter.py — Any model via LiteLLM
  - adapters/local_adapter.py — Local models (Ollama, vLLM endpoint)
  - adapters/base.py — Abstract ModelAdapter with generate() method
  - AC: Can query at least 2 different providers
- [ ] Implement test runner (src/llm_behavior_diff/runner.py)
  - Run test suite against two model versions concurrently
  - Rate limiting, retry logic, cost tracking
  - Progress bar with rich
  - AC: Can run 50 test cases against 2 models in parallel

## Phase 2: Semantic Diff Analysis (Week 1-2)
- [ ] Build semantic comparator (src/llm_behavior_diff/comparators/semantic.py)
  - Sentence embedding similarity (sentence-transformers)
  - Semantic similarity threshold for "same" vs "different"
  - AC: Correctly identifies semantically equivalent but differently worded outputs
- [ ] Build behavioral comparator (src/llm_behavior_diff/comparators/behavioral.py)
  - LLM-as-judge: use a third model to evaluate behavioral differences
  - Categories: tone_shift, knowledge_change, safety_boundary_change, reasoning_change, refusal_change
  - AC: Produces meaningful behavioral diff categories
- [ ] Build factual comparator (src/llm_behavior_diff/comparators/factual.py)
  - Detect factual contradictions between versions
  - Highlight new hallucinations or fixed hallucinations
  - AC: Catches factual regressions
- [ ] Build format comparator (src/llm_behavior_diff/comparators/format.py)
  - Detect structural output changes (JSON schema drift, markdown format changes)
  - AC: Catches output format regressions
- [ ] Implement diff aggregator (src/llm_behavior_diff/aggregator.py)
  - Combine all comparator results
  - Produce per-category regression/improvement scores
  - Statistical significance testing
  - AC: Produces aggregated report with confidence intervals

## Phase 3: Reporting & CLI (Week 2)
- [ ] Build report generator (src/llm_behavior_diff/reporter.py)
  - JSON detailed report
  - HTML interactive report with side-by-side comparisons
  - Markdown summary for PR comments
  - Terminal rich output
  - AC: All formats work
- [ ] Build CLI (src/llm_behavior_diff/cli.py)
  - `llm-diff run --model-a gpt-4o --model-b gpt-4.5 --suite tests.yaml`
  - `llm-diff report <results.json> --format html`
  - `llm-diff compare <result-a.json> <result-b.json>` — compare two runs
  - AC: All commands work
- [ ] Build test suite templates (suites/)
  - suites/general_knowledge.yaml
  - suites/instruction_following.yaml
  - suites/safety_boundaries.yaml
  - suites/coding_tasks.yaml
  - suites/reasoning.yaml
  - AC: At least 10 test cases per suite
- [ ] Write tests (tests/)
  - AC: >80% coverage

## Phase 4: CI/CD & Distribution
- [ ] GitHub Action for model upgrade regression testing
- [ ] GitHub Actions CI
- [ ] Docker image
- [ ] PyPI packaging (`pip install llm-behavior-diff`)

## Phase 5: Documentation & Launch
- [ ] Professional README
- [ ] mkdocs site
- [ ] Launch post for dev.to / HN

## Success Metrics
- Can compare any two LLM versions in under 30 minutes for 100 test cases
- Reports highlight top 10 behavioral regressions/improvements with 95%+ accuracy
- Used in production by at least 3 organizations within 6 months
- <5% false positive rate on behavioral diff detection
