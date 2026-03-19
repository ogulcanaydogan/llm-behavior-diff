# API Reference (Manual)

This page documents the stable, user-facing Python API used in automation scripts and notebooks.

## Runner API

Import path:

```python
from llm_behavior_diff.runner import BehaviorDiffRunner, load_test_suite
```

### `load_test_suite(path: str | Path) -> TestSuite`

- Loads YAML from disk.
- Validates against `TestSuite` schema.
- Raises `ValueError` when file parse/validation fails.

### `BehaviorDiffRunner(...)`

Constructor parameters:

- `model_a: str`
- `model_b: str`
- `judge_model: str | None = None` (optional metadata-only LLM-as-judge)
- `max_workers: int = 4`
- `semantic_threshold: float = 0.85`
- `continue_on_error: bool = False`
- `max_retries: int = 3`
- `rate_limit_rps: float = 0.0`
- `pricing_file: str | Path | None = None`

Main method:

```python
report = await runner.run_suite(test_suite)
```

Returns `BehaviorReport`.

## Schema Models

Import path:

```python
from llm_behavior_diff.schema import (
    TestCase,
    TestSuite,
    DiffResult,
    BehaviorReport,
    BehaviorCategory,
)
```

### `TestCase`

Core fields:

- `id`, `prompt`, `category`, `tags`, `expected_behavior`
- `max_tokens`, `temperature`, `metadata`

### `TestSuite`

Core fields:

- `name`, `description`, `version`, `metadata`, `test_cases`

### `DiffResult`

Core fields include:

- test/model outputs and semantic score
- `behavior_category`, regression/improvement flags
- `metadata.comparators` breakdown (semantic/behavioral/factual/format and optional judge)

### `BehaviorReport`

Core fields include:

- run identity (`model_a`, `model_b`, `suite_name`)
- aggregate counts (`total_tests`, `total_diffs`, `regressions`, `improvements`)
- category breakdowns
- `metadata` values for processed/failed tests, errors, token usage, estimated cost, pricing source, comparator summary
- judge metadata when enabled: `judge_enabled`, `judge_model`, comparator-level judge decisions
- significance metadata: `significance.method/confidence_level/resamples/seed/sample_size`
- significance rate payloads:
  - `significance.regression_rate.point/ci_low/ci_high/p_value_two_sided`
  - `significance.improvement_rate.point/ci_low/ci_high/p_value_two_sided`

Helper methods:

- `regression_rate()`
- `improvement_rate()`
- `top_regression_categories(n)`
- `top_improvement_categories(n)`

## Stability Notes

- CLI output format can evolve, but report JSON schema is kept backward compatible where possible.
- Comparator internals are deterministic, but metadata details can expand over time.
- For long-lived automation, pin package version and validate expected metadata keys.
