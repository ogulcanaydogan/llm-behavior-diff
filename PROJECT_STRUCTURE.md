# Project Structure

Complete overview of the `llm-behavior-diff` repository.

## Directory Tree

```
llm-behavior-diff/
├── docs/                               # Documentation
│   ├── index.md                       # Main documentation
│   └── quickstart.md                  # Quick start guide
│
├── src/llm_behavior_diff/             # Main package
│   ├── __init__.py                    # Package initialization
│   ├── schema.py                      # Pydantic models (TestCase, DiffResult, etc.)
│   ├── cli.py                         # Click CLI commands
│   │
│   ├── adapters/                      # Model provider adapters
│   │   ├── __init__.py
│   │   ├── base.py                    # Abstract ModelAdapter base class
│   │   ├── openai_adapter.py          # OpenAI API implementation
│   │   └── anthropic_adapter.py       # Anthropic API implementation
│   │
│   ├── comparators/                   # Behavioral comparison engines
│   │   ├── __init__.py
│   │   └── semantic.py                # Semantic similarity using embeddings
│   │
│   └── reports/                       # Report generation
│       └── __init__.py
│
├── tests/                             # Test suite
│   ├── __init__.py
│   ├── test_schema.py                 # Schema validation tests
│   ├── comparators/
│   │   ├── __init__.py
│   │   └── test_semantic.py           # Semantic comparator tests
│   └── fixtures/
│       ├── __init__.py
│       └── sample_suite.yaml          # Sample test suite for testing
│
├── suites/                            # Pre-built test suites
│   ├── general_knowledge.yaml         # 10 factual accuracy tests
│   └── instruction_following.yaml     # 10 instruction compliance tests
│
├── .github/
│   └── workflows/
│       └── ci.yml                     # GitHub Actions CI/CD
│
├── Dockerfile                         # Container image definition
├── Makefile                           # Development commands
├── pyproject.toml                     # Python project configuration
├── README.md                          # User-facing readme
├── ROADMAP.md                         # Development roadmap
├── CONTRIBUTING.md                    # Contribution guidelines
├── LICENSE                            # MIT License
├── PROJECT_STRUCTURE.md               # This file
└── .gitignore                         # Git ignore rules
```

## Key Files

### src/llm_behavior_diff/schema.py
Pydantic data models for the entire system:

- `TestCase`: Single test with prompt, category, expected behavior
- `TestSuite`: Collection of test cases
- `ModelResponse`: Response from a model with metadata
- `DiffResult`: Comparison result for one test between two models
- `BehaviorCategory`: Enum of behavior difference types
- `BehaviorReport`: Aggregated results with statistics

### src/llm_behavior_diff/adapters/base.py
Abstract base class that all model adapters inherit from:

```python
class ModelAdapter(ABC):
    async def generate(prompt, max_tokens, temperature, **kwargs) -> tuple[str, Dict]
    async def health_check() -> bool
```

### src/llm_behavior_diff/adapters/openai_adapter.py
Concrete implementation for OpenAI models (GPT-4o, GPT-4.5, etc.)

### src/llm_behavior_diff/adapters/anthropic_adapter.py
Concrete implementation for Anthropic models (Claude 3 family)

### src/llm_behavior_diff/comparators/semantic.py
Semantic similarity comparison using sentence embeddings:

- Uses `sentence-transformers`
- Configurable similarity threshold
- Returns similarity score (0-1) and boolean match

### src/llm_behavior_diff/cli.py
Click-based CLI with three main commands:

1. `llm-diff run` - Run behavioral diff tests
2. `llm-diff report` - Generate reports (json, html, markdown, table)
3. `llm-diff compare` - Compare two reports

### pyproject.toml
Python package configuration:

- Entry point: `llm-diff` command
- Dependencies: pydantic, click, rich, openai, anthropic, litellm, sentence-transformers
- Optional dev dependencies for testing and documentation
- Build system configuration

### tests/
Test coverage for all modules:

- `test_schema.py`: Validates all Pydantic models
- `test_semantic.py`: Tests semantic comparator
- `sample_suite.yaml`: Example test suite for integration testing

### suites/
Pre-built test suites organized by domain:

- `general_knowledge.yaml`: 10 factual knowledge tests
- `instruction_following.yaml`: 10 instruction compliance tests
- Additional suites planned (safety, coding, reasoning)

## Data Flow

```
1. User creates test suite (YAML)
2. CLI loads suite and instantiates adapters
3. Test runner executes tests in parallel:
   - Model A adapter.generate(prompt) → response_a
   - Model B adapter.generate(prompt) → response_b
4. Comparators analyze responses:
   - SemanticComparator: Check semantic equivalence
   - BehavioralComparator: LLM-as-judge evaluation
   - FactualComparator: Detect contradictions
5. Aggregator combines results into BehaviorReport
6. Reporter formats output (JSON, HTML, Markdown, Table)
7. User reviews report and makes deployment decision
```

## Configuration & Environment

### API Keys
Set via environment variables:
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### Model Identifiers
Supported model strings by provider:

**OpenAI**: `gpt-4o`, `gpt-4.5`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`

**Anthropic**: `claude-3-opus`, `claude-3-sonnet`, `claude-3-haiku`

**LiteLLM**: Any model from [litellm providers](https://docs.litellm.ai/docs/providers)

## Testing

Run all tests:
```bash
pytest tests/ -v
```

With coverage:
```bash
pytest tests/ --cov=src/llm_behavior_diff
```

Individual test files:
```bash
pytest tests/test_schema.py -v
pytest tests/comparators/test_semantic.py -v
```

## Development Workflow

1. **Setup**: `make dev`
2. **Code**: Write/edit files
3. **Test**: `make test-cov`
4. **Lint**: `make lint`
5. **Format**: `make format`
6. **Check all**: `make check`
7. **Clean**: `make clean`

## Phases & Feature Roadmap

### Phase 1: Core Engine (Week 1)
- [x] Project setup and structure
- [x] Schema definitions
- [x] Base adapter abstraction
- [x] OpenAI and Anthropic adapters
- [ ] Test runner with concurrency
- [ ] Cost tracking

### Phase 2: Comparators (Week 1-2)
- [x] Semantic comparator (embeddings)
- [ ] Behavioral comparator (LLM-as-judge)
- [ ] Factual comparator (contradiction detection)
- [ ] Format comparator (structure drift)

### Phase 3: Reporting & CLI (Week 2)
- [x] CLI skeleton with commands
- [x] Report generator shell
- [ ] JSON reporting implementation
- [ ] HTML reporting with visualization
- [ ] Markdown PR comment generation
- [ ] Terminal rich output

### Phase 4: Distribution
- [ ] GitHub Actions CI
- [ ] Docker image
- [ ] PyPI packaging
- [ ] GitHub Action for model upgrades

### Phase 5: Documentation & Launch
- [x] README
- [x] Quick start guide
- [x] Contributing guidelines
- [ ] API reference docs
- [ ] Example test suites
- [ ] Blog post/announcement

## Extension Points

### Adding New Comparators
1. Create `src/llm_behavior_diff/comparators/your_comparator.py`
2. Implement comparison logic
3. Add tests in `tests/comparators/test_your_comparator.py`
4. Export in `src/llm_behavior_diff/comparators/__init__.py`

### Adding New Model Adapters
1. Create `src/llm_behavior_diff/adapters/your_provider_adapter.py`
2. Inherit from `ModelAdapter`
3. Implement `generate()` and `health_check()`
4. Add tests in `tests/adapters/test_your_provider.py`
5. Export in `src/llm_behavior_diff/adapters/__init__.py`

### Adding New Test Suites
1. Create `suites/your_domain.yaml`
2. Follow schema in existing suites
3. Include metadata and tags
4. Test with `llm-diff run --suite suites/your_domain.yaml --dry-run`

## Dependencies

### Core
- `pydantic>=2.0.0`: Data validation
- `click>=8.1.7`: CLI framework
- `rich>=13.7.0`: Terminal formatting
- `openai>=1.3.0`: OpenAI API
- `anthropic>=0.7.0`: Anthropic API
- `litellm>=1.3.0`: Multi-provider LLM library
- `sentence-transformers>=2.2.0`: Embeddings
- `numpy>=1.24.0`: Numerical computation
- `pyyaml>=6.0`: YAML parsing

### Development
- `pytest>=7.4.0`: Testing framework
- `pytest-cov>=4.1.0`: Coverage reporting
- `black>=23.7.0`: Code formatting
- `ruff>=0.1.0`: Linting
- `mypy>=1.5.0`: Type checking

## License & Contributing

Licensed under MIT. See LICENSE and CONTRIBUTING.md.

All contributions welcome! Start with an issue or discussion.
