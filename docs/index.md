# llm-behavior-diff Documentation

`llm-behavior-diff` helps you compare two LLM versions on the same suite and detect behavioral regressions before production upgrades.

## Documentation Map

- [Quick Start](quickstart.md)
- [CLI Reference](cli-reference.md)
- [Suite Reference](suite-reference.md)
- [Architecture](architecture.md)
- [API Reference (Manual)](api-reference.md)
- [Release Runbook](release-runbook.md)
- [Launch Kit (current-state dev.to + HN copy)](launch-kit/devto.md)

## What You Can Do

- Run deterministic behavior comparisons (`semantic`, `factual`, `format`, `behavioral`)
- Aggregate regressions/improvements with a fixed precedence policy
- Track token usage and estimated cost metadata
- Generate table/json/html/markdown/csv/ndjson/junit reports
- Enforce upgrade gates in CI using built-in suites

## Fast Example

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite suites/general_knowledge.yaml \
  --output report.json

llm-diff report report.json --format table
```

## Built-In Suites

- `suites/general_knowledge.yaml`
- `suites/instruction_following.yaml`
- `suites/safety_boundaries.yaml`
- `suites/coding_tasks.yaml`
- `suites/reasoning.yaml`

## Notes

- Provider resolver supports OpenAI (`gpt-*`, `o1-*`, `o3-*`) and Anthropic (`claude-*`) legacy ids.
- Provider resolver also supports explicit prefixed ids:
  `litellm:<model_ref>` and `local:<model_ref>`.
- One `--suite` file is processed per `run` command.
- Optional LLM-as-judge is implemented via `--judge-model` as metadata-only signal.
- Bootstrap + Wilson statistical intervals are implemented in run metadata.
- Compare output includes bootstrap delta CI + permutation p-value.
- Launch kit content tracks current implementation state (not historical snapshots).
- No open committed roadmap items currently; future items are tracked as new phases.
