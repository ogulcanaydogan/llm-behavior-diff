# The Missing Layer in LLM Upgrades: Behavioral Diffing Before Rollout

## TL;DR

Most model upgrade incidents are not caused by total failure. They come from subtle behavioral drift:

- format constraints stop being followed
- factual quality changes on sensitive prompts
- refusal boundaries move
- output style changes in ways that break downstream logic

`llm-behavior-diff` is a deterministic comparator-first tool that makes these changes visible before shipping.

## The Problem

A typical upgrade process runs a handful of prompts, checks for obvious regressions, and moves on. That misses structured drift patterns.

Two outputs can both look "reasonable" while one breaks product assumptions. Teams need:

- repeatable suites
- explicit regression/improvement classification
- machine-readable artifacts for CI gates

## Approach

The tool runs the same suite on model A and model B, then classifies each test using deterministic comparators:

1. `semantic` (same meaning gate)
2. `factual` (hallucination/knowledge-change rules)
3. `format` (JSON/table/count/yes-no constraints)
4. `behavioral` (expected-behavior coverage deltas)

Final decision uses fixed precedence:

`semantic-same > factual > format > behavioral > unknown`

No LLM-as-judge in this version. The focus is explainability and stable costs.

## Example Run

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite suites/instruction_following.yaml \
  --max-retries 3 \
  --rate-limit-rps 2 \
  --output instruction_report.json
```

Then render:

```bash
llm-diff report instruction_report.json --format table
```

Example summary shape:

```text
Total Tests: 10
Total Differences: 4
Regressions: 1
Improvements: 2
Failed Tests: 0
```

## CI Gate Pattern

The repo includes a model-upgrade workflow that runs all built-in suites and fails if any regression exists.

Gate rule:

- regressions > 0 => fail
- regressions = 0 => pass

This makes upgrade risk explicit instead of subjective.

## Release/Distribution Status

Implemented:

- core CI on PR + master
- release-check workflow (build + twine + wheel smoke)
- manual PyPI workflow
- Docker build/smoke + optional GHCR push

## Lessons Learned

1. Deterministic first is practical.
   - You can reason about failures quickly.
2. Metadata is as important as scores.
   - token usage, cost estimate, and per-comparator decisions matter in operations.
3. Fail-fast + continue-on-error should both exist.
   - fail-fast for strict gates, continue mode for exploratory runs.

## Known Limits

- No LLM-as-judge mode yet.
- No statistical significance layer yet.
- Factual comparator is deterministic heuristics only (no external fact API).

## Planned Next

- optional LLM-as-judge comparator
- statistical confidence/significance reporting
- broader adapter coverage

## If You Want to Try It

1. install package
2. run built-in suites one by one with your current and candidate models
3. inspect regressions by category
4. gate deployment on explicit thresholds

Docs:

- `docs/quickstart.md`
- `docs/cli-reference.md`
- `docs/release-runbook.md`
