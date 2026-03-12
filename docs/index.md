# llm-behavior-diff Documentation

## Overview

`llm-behavior-diff` is a behavioral regression testing tool for LLM model upgrades. It compares two model versions on the same test suite and produces detailed semantic diff reports.

## Quick Links

- [Installation](installation.md)
- [Quick Start](quickstart.md)
- [CLI Reference](cli.md)
- [Test Suites](test-suites.md)
- [Architecture](architecture.md)
- [API Reference](api.md)
- [Contributing](../CONTRIBUTING.md)

## What Problem Does It Solve?

When you upgrade from GPT-4o to GPT-4.5, or Claude 3 Sonnet to Opus, you need to know:

1. What changed in model behavior?
2. Are there regressions in reasoning, safety, or factual accuracy?
3. What improved?
4. Is it safe to upgrade in production?

Traditional testing can't answer these questions — you need semantic diff analysis.

## Key Features

- **Multi-provider support**: OpenAI, Anthropic, LiteLLM, local models
- **Semantic analysis**: Detects meaningful differences, not just string differences
- **Behavioral categories**: Classifies changes (tone, knowledge, safety, etc.)
- **Aggregated reports**: JSON, HTML, Markdown, terminal output
- **Concurrent testing**: Run tests in parallel for speed
- **Cost tracking**: Monitor API usage across comparisons

## Example

```bash
# Compare GPT-4o to GPT-4.5
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite suites/general_knowledge.yaml \
  --output report.json

# Generate HTML report
llm-diff report report.json --format html -o report.html
```

Result:
```
Total Tests: 50
Regressions: 2 (4.0%)
Improvements: 4 (8.0%)

Top Regressions:
  - reasoning_change: 1
  - instruction_following: 1
```

## Architecture

```
┌─────────────────┐
│  Test Suite     │
│  (YAML)         │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│   Test Runner               │
│   - Load suite              │
│   - Run in parallel         │
│   - Call adapters           │
└────────┬────────────────────┘
         │
    ┌────┴─────┐
    │           │
    ▼           ▼
┌──────────┐ ┌──────────────┐
│ Model A  │ │  Model B     │
│ Adapter  │ │  Adapter     │
└────┬─────┘ └──────┬───────┘
     │              │
     ▼              ▼
 ┌──────────────────────┐
 │  Get Responses       │
 │  (OpenAI, etc.)      │
 └──────┬───────────────┘
        │
        ▼
 ┌────────────────────────────────────┐
 │  Comparators                       │
 │  - Semantic (embeddings)           │
 │  - Behavioral (LLM-as-judge)       │
 │  - Factual (contradiction detect)  │
 │  - Format (structure drift)        │
 └──────┬─────────────────────────────┘
        │
        ▼
 ┌────────────────────────────────────┐
 │  Aggregator                        │
 │  - Combine results                 │
 │  - Calculate stats                 │
 │  - Generate report                 │
 └──────┬─────────────────────────────┘
        │
        ▼
 ┌────────────────────────────────────┐
 │  Report Generator                  │
 │  - JSON, HTML, Markdown, Terminal  │
 └────────────────────────────────────┘
```

## Behavior Categories

When a difference is detected, it's classified into one of these categories:

| Category | Description |
|----------|-------------|
| SEMANTIC | Same meaning, different wording |
| TONE_SHIFT | Change in formality or tone |
| KNOWLEDGE_CHANGE | New or lost knowledge |
| SAFETY_BOUNDARY | Changed refusal/safety behavior |
| REASONING_CHANGE | Different reasoning approach |
| INSTRUCTION_FOLLOWING | Changed compliance |
| FORMAT_CHANGE | Output structure changed |
| HALLUCINATION_NEW | New factual errors |
| HALLUCINATION_FIXED | Fixed factual errors |

## Next Steps

1. [Install](installation.md) the package
2. Follow the [Quick Start](quickstart.md) guide
3. Create your first test suite
4. Run your first comparison
5. Explore [advanced features](test-suites.md)
