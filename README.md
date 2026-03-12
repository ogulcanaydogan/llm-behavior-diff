# llm-behavior-diff

> **The `git diff` for LLM behavior.** When you upgrade a model version, know exactly what changed — not just outputs, but reasoning patterns, safety boundaries, factual accuracy, and instruction following.

Essential tool for enterprise MLOps when upgrading language models in production.

## What It Does

`llm-behavior-diff` runs a test suite against two model versions and produces a **semantic diff report** showing:

- **Semantic differences**: Differently worded but equivalent responses
- **Behavioral regressions**: Model became worse at something
- **Behavioral improvements**: Model became better at something
- **Factual changes**: New hallucinations, fixed errors
- **Format drift**: Output structure changed
- **Safety boundary shifts**: Changes in refusal/safety behavior

### Example Report

```
Behavioral Diff Report: gpt-4o vs gpt-4.5
===========================================

Total Tests: 50
Total Differences: 8
Regressions: 2 (4.0%)
Improvements: 4 (8.0%)

Top Regressions:
  - reasoning_change: 1
  - instruction_following: 1

Top Improvements:
  - knowledge_change: 2
  - hallucination_fixed: 2
```

## Installation

```bash
pip install llm-behavior-diff
```

Requires Python 3.11+

## Quick Start

### 1. Define a test suite

Create `tests.yaml`:

```yaml
name: general_knowledge
description: General knowledge tests
test_cases:
  - id: test_001
    prompt: "What is the capital of France?"
    category: factual
    tags: [geography]
    expected_behavior: Should correctly identify Paris
    max_tokens: 256
    temperature: 0.0
```

### 2. Run behavioral diff

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite tests.yaml \
  --output report.json
```

### 3. Generate report

```bash
llm-diff report report.json --format html -o report.html
llm-diff report report.json --format markdown
```

## CLI Commands

### `llm-diff run`

Run behavioral regression tests comparing two models.

```bash
llm-diff run \
  --model-a gpt-4o \
  --model-b gpt-4.5 \
  --suite tests.yaml \
  --output results.json \
  --max-workers 4
```

**Options:**
- `--model-a`: First model identifier (e.g., 'gpt-4o', 'claude-3-opus')
- `--model-b`: Second model for comparison
- `--suite`: Path to test suite YAML
- `--output`: Output file for results (JSON)
- `--max-workers`: Concurrent API calls (default: 4)
- `--dry-run`: Validate suite without running

### `llm-diff report`

Generate formatted reports from results.

```bash
llm-diff report results.json --format html -o report.html
```

**Formats:**
- `table`: Rich terminal table (default)
- `json`: Detailed JSON
- `html`: Interactive HTML report
- `markdown`: Markdown for PR comments

### `llm-diff compare`

Compare two behavioral diff reports.

```bash
llm-diff compare results_v1.json results_v2.json -o comparison.html
```

## Test Suite Format

Test suites are YAML files defining behavioral expectations:

```yaml
name: suite_name
description: Suite description
version: "1.0"

test_cases:
  - id: test_001
    prompt: "Input prompt"
    category: factual_knowledge  # or explanation, instruction_following, etc.
    tags: [tag1, tag2]
    expected_behavior: "Description of expected behavior (not exact output)"
    max_tokens: 2048
    temperature: 0.7
    metadata:
      difficulty: easy  # or medium, hard
      requires_current_knowledge: false
```

**Key point**: `expected_behavior` describes what you want the model to do, not the exact output. The tool compares semantic meaning, not word-for-word outputs.

## Supported Models

### OpenAI
- `gpt-4o`, `gpt-4.5`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`

### Anthropic
- `claude-3-opus`, `claude-3-sonnet`, `claude-3-haiku`

### Via LiteLLM
Any model supported by [litellm](https://github.com/BerriAI/litellm) including:
- Cohere, Replicate, Together, HuggingFace, Aleph Alpha, Baseten, Voxel51...

### Local/Self-Hosted
- Ollama endpoints
- vLLM servers
- Any OpenAI-compatible API

## How It Works

1. **Test Runner**: Runs test suite against both models in parallel
2. **Semantic Analysis**: Compares responses using sentence embeddings
3. **Behavioral Scoring**: Uses LLM-as-judge to evaluate behavioral differences
4. **Diff Aggregation**: Combines results into unified report
5. **Report Generation**: Creates interactive reports in multiple formats

### Behavior Categories

- **SEMANTIC**: Same meaning, different wording
- **TONE_SHIFT**: Change in formality/tone
- **KNOWLEDGE_CHANGE**: New or lost information
- **SAFETY_BOUNDARY**: Refusal behavior changed
- **REASONING_CHANGE**: Different reasoning approach
- **INSTRUCTION_FOLLOWING**: Compliance change
- **FORMAT_CHANGE**: Output structure changed
- **HALLUCINATION_NEW**: New factual errors
- **HALLUCINATION_FIXED**: Factual errors fixed

## Configuration

### API Keys

Set via environment variables:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

Or pass to config:

```python
from llm_behavior_diff.adapters import ModelAdapterConfig

config = ModelAdapterConfig(
    api_key="sk-...",
    timeout=60,
    max_retries=3
)
```

### Custom Test Suites

Pre-built suites included:

- `suites/general_knowledge.yaml`: Factual accuracy (10 tests)
- `suites/instruction_following.yaml`: Format compliance (10 tests)
- `suites/safety_boundaries.yaml`: Refusal behavior (TBD)
- `suites/coding_tasks.yaml`: Code generation (TBD)
- `suites/reasoning.yaml`: Multi-step reasoning (TBD)

## Python API

```python
from llm_behavior_diff.adapters import OpenAIAdapter, AnthropicAdapter
from llm_behavior_diff.schema import TestSuite, TestCase

# Load test suite
suite = TestSuite.model_validate_yaml(open("tests.yaml").read())

# Create adapters
model_a = OpenAIAdapter("gpt-4o")
model_b = OpenAIAdapter("gpt-4.5")

# Run tests
# TODO: Implement runner
```

## Development

### Setup

```bash
git clone https://github.com/your-org/llm-behavior-diff
cd llm-behavior-diff
pip install -e ".[dev]"
```

### Tests

```bash
pytest tests/ -v --cov=src/llm_behavior_diff
```

### Code Style

```bash
black src/ tests/
ruff check src/ tests/
mypy src/
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for detailed development plan.

**Phase 1** (Week 1): Core diff engine, schema, adapters, test runner
**Phase 2** (Week 1-2): Semantic, behavioral, factual, format comparators
**Phase 3** (Week 2): Reporting, CLI, test suites, tests
**Phase 4**: CI/CD, Docker, PyPI
**Phase 5**: Docs, mkdocs, launch

## FAQ

**Q: Can I use this with closed-source APIs?**
A: Yes! Works with OpenAI, Anthropic, and any API with compatible adapters.

**Q: What about cost?**
A: Comparing 100 test cases against 2 models costs roughly the same as running those tests once. Track costs in reports.

**Q: How do I handle rate limits?**
A: Configure `max_workers` (default 4) and `timeout` to manage concurrency.

**Q: Can I extend with custom comparators?**
A: Yes, implement `BaseComparator` interface for custom logic.

## License

MIT

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

## Citation

If you use llm-behavior-diff in research, please cite:

```bibtex
@software{llm_behavior_diff,
  title = {llm-behavior-diff: Behavioral Regression Testing for LLM Upgrades},
  author = {Contributors},
  year = {2024},
  url = {https://github.com/your-org/llm-behavior-diff}
}
```
