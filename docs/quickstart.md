# Quick Start Guide

Get up and running with `llm-behavior-diff` in 5 minutes.

## 1. Installation

```bash
pip install llm-behavior-diff
```

Requires Python 3.11+

## 2. Set API Keys

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

## 3. Create a Test Suite

Create `my_tests.yaml`:

```yaml
name: quick_test
description: Quick test suite
test_cases:
  - id: test_001
    prompt: "What is the capital of France?"
    category: factual
    tags: [geography]
    expected_behavior: Should correctly identify Paris
    max_tokens: 256
    temperature: 0.0

  - id: test_002
    prompt: "Summarize photosynthesis in 1 sentence"
    category: explanation
    tags: [science]
    expected_behavior: Should explain that photosynthesis converts light to energy
    max_tokens: 256
    temperature: 0.3

  - id: test_003
    prompt: "List 3 Python web frameworks"
    category: knowledge
    tags: [coding]
    expected_behavior: Should list Django, Flask, FastAPI or similar frameworks
    max_tokens: 512
    temperature: 0.5
```

## 4. Run the Comparison

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4-turbo \
  --suite my_tests.yaml \
  --output results.json
```

This will:
1. Load your test suite
2. Run each test against both models in parallel
3. Compare the responses
4. Generate a JSON report

## 5. View the Report

### Terminal Output (Recommended)

```bash
llm-diff report results.json --format table
```

Output:
```
Behavioral Diff Report: gpt-4o vs gpt-4-turbo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Metric                  Value
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Test Suite              quick_test
Total Tests             3
Total Differences       1
Regressions             1 (33.3%)
Improvements            0
Duration                12.3s
```

### HTML Report

```bash
llm-diff report results.json --format html -o report.html
open report.html
```

### JSON Report

```bash
llm-diff report results.json --format json
```

## What Each Model Sees

Each test is run independently against both models:

```
Test: "What is the capital of France?"
├─ Model A (gpt-4o) → "The capital of France is Paris."
└─ Model B (gpt-4-turbo) → "Paris is the capital of France."

Comparison:
├─ Semantic Similarity: 0.98 (>0.85 threshold = semantically same)
├─ Is Regression: No
├─ Is Improvement: No
└─ Category: SEMANTIC
```

## Understanding Results

### Regression
A test case where model B performs worse than model A.

Example:
```
Model A: "Mars has two moons: Phobos and Deimos"
Model B: "Mars has three moons"
Regression: true (factual error introduced)
```

### Improvement
A test case where model B performs better than model A.

Example:
```
Model A: "Python is a language"
Model B: "Python is a high-level, interpreted programming language"
Improvement: true (more detailed, accurate response)
```

### Semantic Only
Different wording but same meaning — not a concern.

Example:
```
Model A: "The sky is blue"
Model B: "Blue is the color of the sky"
Difference: true (semantic only)
Regression: false
```

## Common Workflows

### Scenario 1: Pre-Release Testing

Before deploying GPT-4.5:

```bash
# Run comprehensive tests
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite suites/general_knowledge.yaml \
  --suite suites/instruction_following.yaml \
  --suite suites/coding_tasks.yaml \
  --output upgrade_check.json

# Review report
llm-diff report upgrade_check.json --format html -o upgrade_report.html
```

Safe to upgrade if regressions < 5%

### Scenario 2: A/B Testing in Production

Compare live model performance:

```bash
# Run against production dataset samples
llm-diff run \
  --model-a claude-3-sonnet \
  --model-b claude-3-opus \
  --suite suites/customer_queries.yaml \
  --output prod_comparison.json

# Decide which to scale
```

### Scenario 3: Regression Testing After Fine-Tuning

Ensure fine-tuning didn't break anything:

```bash
llm-diff run \
  --model-a base-model \
  --model-b fine-tuned-model \
  --suite suites/my_domain.yaml \
  --output ft_results.json
```

## Test Suite Best Practices

1. **Use Behavioral Expectations** (not exact outputs)
   ```yaml
   # Good
   expected_behavior: "Should explain the three laws of thermodynamics"

   # Bad
   expected_behavior: "The first law states..."
   ```

2. **Include Edge Cases**
   - Ambiguous questions
   - Adversarial inputs
   - Multi-step reasoning
   - Safety-critical queries

3. **Organize by Category**
   - `factual_knowledge`: Basic facts
   - `reasoning`: Multi-step logic
   - `instruction_following`: Format compliance
   - `safety`: Refusal behavior

4. **Tag for Filtering**
   ```yaml
   tags: [important, regression_critical, performance]
   ```

5. **Set Appropriate Temperature**
   - `0.0` for factual/deterministic
   - `0.3-0.5` for balanced
   - `0.7+` for creative

## Troubleshooting

### "API key not found"
```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

### "Model not found"
Check model name is valid for the provider:
```bash
llm-diff run --model-a gpt-4o --model-b gpt-4.5 ...
# ✓ Both are valid OpenAI models
```

### "Timeout"
Increase timeout or reduce concurrent tests:
```bash
llm-diff run ... --max-workers 2
```

### "Rate limited"
Reduce `--max-workers` and try again:
```bash
llm-diff run ... --max-workers 1
```

## Next Steps

- Read [Test Suite Format Reference](test-suites.md)
- Explore [CLI Commands](cli.md)
- Learn [Architecture](architecture.md)
- Check [Pre-built Test Suites](../suites/)
- Contribute your own suites!
