# Show HN Launch Pack

## Title Options

1. Show HN: llm-behavior-diff — deterministic upgrade regression testing for LLMs
2. Show HN: Comparator-first LLM behavior diffs with CI gating and report artifacts
3. Show HN: A practical model-upgrade gate for LLM apps (deterministic + optional judge)

## HN Submission Draft

I built `llm-behavior-diff`, a CLI for comparing two LLM versions on the same suite before rollout.

Core design:

- deterministic comparator-first final decisions (`semantic`, `factual`, `format`, `behavioral`)
- optional `--judge-model` layer for extra signal (metadata-only, non-fatal, never overrides final decision)
- bootstrap + Wilson intervals in run metadata and bootstrap delta CI + permutation p-values in compare output

It outputs JSON artifacts for CI and supports strict upgrade gates (example: fail when regressions > 0).

Workflows included in the repo:

- core CI on PR/master
- release-check (build/twine/wheel smoke)
- manual PyPI publish
- Docker build/smoke + optional GHCR push
- model-upgrade regression workflow with suite artifacts

I’d value feedback on:

1. deterministic vs judge weighting in production sign-off
2. practical regression gate policies at different risk tiers
3. what audit metadata is required in real release reviews

## Likely Questions and Short Answers

### Why keep deterministic as final decision?

Deterministic precedence is predictable and reproducible in CI. Judge is available for extra context without changing final flags.

### Is LLM-as-judge implemented?

Yes, opt-in via `--judge-model`. It runs only on semantic diffs and writes comparator metadata.

### Is significance implemented?

Yes. Run metadata includes bootstrap + Wilson intervals, and compare prints bootstrap delta CI plus permutation p-value rows when `diff_results` are available.

### Which providers are supported now?

Current resolver supports:

- OpenAI prefixes (`gpt-*`, `o1-*`, `o3-*`)
- Anthropic prefixes (`claude-*`)
- explicit LiteLLM refs (`litellm:<model_ref>`)
- explicit local OpenAI-compatible refs (`local:<model_ref>`)

### How are transient failures handled?

Retry with exponential backoff + jitter, optional per-model rate limiting, and optional continue-on-error mode.
