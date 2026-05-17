# Quantization INT8 Example

Example behavioral diff suite for comparing an INT8-quantized model against
its FP16 baseline. Designed to be executed with `--quantization int8` so the
calibrated profile takes effect.

## Why this exists

A vanilla `llm-diff run` between an FP16 model and its INT8 counterpart
typically over-reports regressions: quantization paraphrases freely
(semantic threshold violated), nudges JSON whitespace (format strict
violated), and tweaks behavioral coverage by a few percent. None of those
are real regressions when the underlying change is a numerics swap.

The `--quantization int8` profile re-tunes the comparators for this case:

| Setting | Default | int8 profile |
| --- | ---: | ---: |
| Semantic threshold | 0.85 | 0.92 |
| Behavioral regression threshold | -0.20 | -0.10 |
| Factual regression threshold | -0.20 | -0.05 |
| Format strict | true | false |
| Factual weight | 1.0 | 1.5 |

Factual checks become **stricter** (quantization must not change facts),
while semantic and format checks become **looser** (paraphrase and minor
format drift are tolerated).

## Running it

```bash
llm-diff run \
  --model-a meta-llama/Llama-3.1-8B-Instruct \
  --model-b meta-llama/Llama-3.1-8B-Instruct-int8 \
  --suite examples/quantization-int8/suite.yaml \
  --quantization int8 \
  --output report.json

llm-diff report report.json --format markdown
llm-diff report report.json --format html --output report.html
```

The rendered report includes a `Quantization Profile` section that surfaces
the calibrated thresholds and weight overrides, so reviewers can see at a
glance which profile produced the verdict.

## What the suite covers

The 8 test cases probe the four scenarios quantization most commonly
affects:

1. **Factual recall** (`q8_factual_*`, `q8_history_*`) — must hold after
   quantization. The stricter factual threshold (-0.05) and 1.5x weight
   catch any factual degradation.
2. **Format compliance** (`q8_format_*`) — minor JSON whitespace and
   yes/no punctuation drift is acceptable; `format_strict=false` prevents
   false-positive regressions.
3. **Reasoning correctness** (`q8_reasoning_001`) — arithmetic and
   step-by-step reasoning are stress tests for INT8 numerical fidelity.
4. **Semantic paraphrase** (`q8_paraphrase_*`) — phrasing drift is
   normal at INT8; the higher semantic threshold (0.92) plus tolerant
   weight (0.8x) keeps these from being flagged as regressions.

## Interpreting the report

After running with `--quantization int8`, the most informative signals
are:

- **Factual regressions in any `q8_factual_*` or `q8_history_*` case**:
  This is a real regression. INT8 should not change well-known facts; if
  it does, the quantization may be miscalibrated or the calibration set
  was too narrow.
- **`semantic` decisions of `semantic_diff` on `q8_paraphrase_*` cases**:
  Often expected at INT8. Inspect the responses; if the meaning is the
  same, this is a paraphrase, not a regression.
- **`format_change` on `q8_format_*` cases**: Marked but not classified
  as regression under int8 (because `format_strict=false`). Worth a human
  glance to confirm structural validity.
