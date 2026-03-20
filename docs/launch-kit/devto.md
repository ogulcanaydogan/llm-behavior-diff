# The Missing Layer in LLM Upgrades: Behavioral Diffing Before Rollout

## TL;DR

Most model upgrade incidents are not full outages. They are behavioral drift:

- format constraints start failing
- factual reliability moves on sensitive prompts
- refusal boundaries shift
- output style changes break downstream assumptions

`llm-behavior-diff` is a comparator-first tool that makes those shifts explicit before rollout.

## The Problem

Many teams still do upgrade checks with a handful of manual prompts. That catches obvious breakage but misses systematic drift patterns.

Two answers can both look acceptable while only one is deploy-safe for your product contracts.

## Approach

The tool runs one suite against model A and model B, then classifies each test with deterministic comparators:

1. `semantic` (same-meaning gate)
2. `factual` (hallucination and knowledge-change rules)
3. `format` (JSON/table/count/yes-no constraints)
4. `behavioral` (expected-behavior coverage delta)

Final decision precedence is fixed:

`semantic-same > factual > format > behavioral > unknown`

This keeps the final category and regression flags explainable and reproducible.

## Optional LLM-as-Judge (Metadata-Only)

Judge is available as an opt-in layer with `--judge-model`.

- runs only when semantic comparator says responses differ
- writes `comparators.judge` metadata (`A | B | TIE | UNKNOWN` mapped decisions)
- non-fatal on parse/timeout/provider errors (`judge_error` or `judge_uncertain`)
- never overrides deterministic final classification

## Example Run

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --judge-model gpt-4o-mini \
  --suite suites/instruction_following.yaml \
  --max-retries 3 \
  --rate-limit-rps 2 \
  --output instruction_report.json
```

Then render and compare:

```bash
llm-diff report instruction_report.json --format table
llm-diff compare baseline.json instruction_report.json
```

Example significance shape:

```text
run metadata:
- regression_rate: point=0.10, ci=[0.04, 0.17]
- improvement_rate: point=0.06, ci=[0.02, 0.12]

compare output:
- regression delta CI: [+1.8, +8.7] pp
- regression delta significant?: yes
```

## CI Gate Pattern

The repository includes a model-upgrade workflow that runs built-in suites and applies a strict gate:

- regressions > 0 => fail
- regressions = 0 => pass

Suite reports are uploaded as artifacts for audit and debugging.

## Release/Distribution Status

Implemented:

- core CI on PR + master
- release-check workflow (build + twine + wheel smoke)
- manual PyPI workflow
- Docker build/smoke + optional GHCR push
- model-upgrade regression workflow

## Known Limits

- factual comparator is deterministic heuristics only (no external fact API)
- significance layer is metadata-only (does not enforce pass/fail by itself)
- advanced methods beyond bootstrap/Wilson/permutation are not included in this version

## Planned Next

- organization-specific policy packs and custom policy plugin hooks
- optional external factual validation connectors
- broader enterprise reporting/export integrations

## If You Want to Try It

1. install package
2. run built-in suites with your baseline and candidate models
3. inspect regressions by category and comparator metadata
4. gate deployment using explicit regression policy in CI

Docs:

- `docs/quickstart.md`
- `docs/cli-reference.md`
- `docs/release-runbook.md`
