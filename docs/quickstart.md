# Quick Start

Set up and run your first behavioral diff in a few minutes.

## 1) Install

```bash
pip install llm-behavior-diff
```

Requires Python 3.11+.

## 2) Configure Provider Keys

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

Optional for local OpenAI-compatible targets:

```bash
export LLM_DIFF_LOCAL_BASE_URL=http://localhost:11434/v1
# optional:
# export LLM_DIFF_LOCAL_API_KEY=local-api-key
```

## 3) Create a Suite File

Create `my_tests.yaml`:

```yaml
name: quick_test
description: Quick behavioral regression suite
version: "1.0"
metadata:
  owner: local-dev

test_cases:
  - id: test_001
    prompt: "What is the capital of France?"
    category: factual
    tags: [geography]
    expected_behavior: Must identify Paris as the capital
    max_tokens: 256
    temperature: 0.0
    metadata:
      priority: high

  - id: test_002
    prompt: "Summarize photosynthesis in one sentence."
    category: explanation
    tags: [science]
    expected_behavior: Must mention converting light into chemical energy
    max_tokens: 256
    temperature: 0.2
    metadata:
      priority: medium
```

## 4) Validate Suite (Dry Run)

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite my_tests.yaml \
  --dry-run
```

## 5) Execute Comparison

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite my_tests.yaml \
  --max-workers 4 \
  --max-retries 3 \
  --rate-limit-rps 2 \
  --output results.json
```

## 6) Render Results

```bash
llm-diff report results.json --format table
llm-diff report results.json --format html -o report.html
llm-diff report results.json --format markdown -o report.md
```

## Compare Two Runs

```bash
llm-diff compare before.json after.json
llm-diff compare before.json after.json -o compare.md
```

## Run All Built-In Suites (One by One)

```bash
llm-diff run --model-a gpt-4o --model-b gpt-4.5 --suite suites/general_knowledge.yaml --output general.json
llm-diff run --model-a gpt-4o --model-b gpt-4.5 --suite suites/instruction_following.yaml --output instruction.json
llm-diff run --model-a gpt-4o --model-b gpt-4.5 --suite suites/safety_boundaries.yaml --output safety.json
llm-diff run --model-a gpt-4o --model-b gpt-4.5 --suite suites/coding_tasks.yaml --output coding.json
llm-diff run --model-a gpt-4o --model-b gpt-4.5 --suite suites/reasoning.yaml --output reasoning.json
```

## Optional: Pricing Override

Create `pricing.yaml`:

```yaml
gpt-4o:
  input_per_1m: 5.0
  output_per_1m: 15.0
```

Use it in `run`:

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite my_tests.yaml \
  --pricing-file pricing.yaml \
  --output priced_results.json
```

## Optional: Metadata-Only LLM Judge

Enable optional judge scoring for semantic-diff cases:

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --judge-model gpt-4o-mini \
  --suite my_tests.yaml \
  --output judged_results.json
```

Judge outcomes are written into `metadata.comparators.judge` and do not override deterministic final classification.

## Optional: Explicit LiteLLM / Local Model IDs

You can route via explicit prefixes:

```bash
llm-diff run \
  --model-a litellm:openai/gpt-4o-mini \
  --model-b local:llama3.1 \
  --suite my_tests.yaml \
  --output prefixed_results.json
```

## Next Reads

- [CLI Reference](cli-reference.md)
- [Suite Reference](suite-reference.md)
- [Architecture](architecture.md)
- [Release Runbook](release-runbook.md)

## Local Dev / CI Parity (Optional)

For repository contributors:

```bash
make install-dev
make ci-local
```
