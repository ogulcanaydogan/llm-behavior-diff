# Suite Reference

A suite is a YAML document validated by `TestSuite` and consumed by `llm-diff run`.

## Required Top-Level Fields

- `name`: suite identifier
- `description`: short description
- `version`: suite version string
- `metadata`: free-form metadata object
- `test_cases`: list of test definitions

## Required Test Case Fields

- `id`: unique id within suite
- `prompt`: prompt string
- `category`: behavior category string
- `tags`: list of tags
- `expected_behavior`: must-have behavior description
- `max_tokens`: integer > 0
- `temperature`: float between `0.0` and `1.0`
- `metadata`: free-form metadata object

## Example

```yaml
name: example_suite
description: Example behavioral regression suite
version: "1.0"
metadata:
  owner: llm-platform

test_cases:
  - id: ex_001
    prompt: "Return valid JSON with keys name and age."
    category: instruction_following
    tags: [json, format]
    expected_behavior: Must return parseable JSON and include name age keys
    max_tokens: 256
    temperature: 0.0
    metadata:
      priority: high
```

## Built-In Suites

- `suites/general_knowledge.yaml`
- `suites/instruction_following.yaml`
- `suites/safety_boundaries.yaml`
- `suites/coding_tasks.yaml`
- `suites/reasoning.yaml`

Each built-in suite has 10 test cases and can be validated with:

```bash
llm-diff run --model-a gpt-4o --model-b gpt-4.5 --suite suites/general_knowledge.yaml --dry-run
```

## Authoring Rules

- Keep prompts time-stable where possible (avoid current-events dependency).
- Write `expected_behavior` as explicit must-have terms/constraints.
- Keep ids deterministic and unique.
- Prefer focused categories (`factual`, `instruction_following`, `safety`, `reasoning`, etc.).

## Validation Checklist

- Suite parses via `load_test_suite`.
- All required fields are present.
- `max_tokens > 0` and temperature is within range.
- No duplicate test ids.
- `prompt` and `expected_behavior` are non-empty.
