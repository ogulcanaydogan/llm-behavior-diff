# Show HN Draft Pack

## Title Options

1. Show HN: llm-behavior-diff – deterministic regression testing for LLM upgrades
2. Show HN: A comparator-first tool to diff behavior between LLM versions
3. Show HN: CI-friendly behavioral diffing for model upgrade safety

## HN Submission Draft

I built `llm-behavior-diff`, a small tool for comparing two LLM versions on the same test suite before production upgrades.

It focuses on deterministic behavior classification (not LLM-as-judge in this version):

- semantic equivalence
- factual drift rules
- format/constraint checks
- expected-behavior coverage deltas

It outputs JSON artifacts and supports CI gating (example policy: fail upgrade if regressions > 0).

Current workflows in the repo:

- core CI on PR/master
- release-check (build/twine/wheel smoke)
- manual PyPI publish
- Docker build/smoke + optional GHCR push
- model-upgrade regression workflow with suite artifacts

I’d especially like feedback on:

1. deterministic-vs-judge tradeoffs
2. regression gate policy design in production
3. what metadata teams need for upgrade sign-off

## Likely Questions and Short Answers

### Why not use an LLM judge directly?

Deterministic first keeps the behavior explainable and cheap. LLM-as-judge is planned as an optional layer.

### Is this only for OpenAI models?

Current provider resolver supports OpenAI (`gpt-*`, `o1-*`, `o3-*`) and Anthropic (`claude-*`).

### How do you handle transient API failures?

Retry with exponential backoff + jitter, optional rate limiting, and optional continue-on-error mode.

### Is there a hard upgrade gate?

Yes. The model-upgrade workflow can fail if total regressions > 0.
