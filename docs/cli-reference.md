# CLI Reference

`llm-diff` provides three commands:

- `run`: execute a suite against two models and write a JSON report
- `report`: render one JSON report in table/json/html/markdown
- `compare`: compare two JSON reports and show metric deltas

## Global

```bash
llm-diff --help
llm-diff --version
```

## `llm-diff run`

Run one suite file per command.

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite suites/general_knowledge.yaml \
  --output report.json
```

Options:

- `--model-a` (required): baseline model id
- `--model-b` (required): candidate model id
- `--suite` (required): suite YAML path
- `--output`, `-o`: output JSON path (default `llm_behavior_diff_report.json`)
- `--max-workers`: test-case parallelism (default `4`)
- `--dry-run`: validate suite only
- `--continue-on-error`: continue suite when a test fails
- `--max-retries`: transient call retry count (default `3`)
- `--rate-limit-rps`: per-model request rate limit, `0` disables it (default `0`)
- `--pricing-file`: optional YAML/JSON pricing override file
- `--judge-model`: optional LLM-as-judge model id (metadata-only, non-fatal, semantic-diff tests only)

### Dry Run

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite suites/general_knowledge.yaml \
  --dry-run
```

## `llm-diff report`

Render a single run report.

```bash
llm-diff report report.json --format table
llm-diff report report.json --format markdown -o report.md
llm-diff report report.json --format html -o report.html
```

Options:

- `report_file` (required): JSON report path
- `--format`: `table` (default), `json`, `html`, `markdown`
- `--output`, `-o`: output file path (stdout when omitted)

`report` table/markdown output includes run-level bootstrap confidence intervals when
`metadata.significance` is present.

## `llm-diff compare`

Compare two report files.

```bash
llm-diff compare before.json after.json
llm-diff compare before.json after.json -o comparison.md
```

Options:

- `result_a` (required): run A JSON
- `result_b` (required): run B JSON
- `--output`, `-o`: optional markdown summary output path

`compare` computes bootstrap delta significance on-the-fly from `diff_results`
when both reports include non-empty test-level outcomes.

## Exit Behavior

- Invalid input/suite/report parsing returns non-zero exit.
- `run` fail-fast is default; set `--continue-on-error` for partial progress mode.
- `--judge-model` never overrides deterministic final category/regression flags; it only adds metadata.
- `compare` includes cost delta row only when both reports include cost metadata.
- `compare` includes significance rows only when both reports include non-empty `diff_results`.
