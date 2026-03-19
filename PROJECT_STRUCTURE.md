# Project Structure

Complete overview of the `llm-behavior-diff` repository.

## Directory Tree

```
llm-behavior-diff/
├── docs/                               # Documentation
│   ├── index.md                       # Documentation home
│   ├── quickstart.md                  # Quick start guide
│   ├── cli-reference.md               # CLI command and flag reference
│   ├── suite-reference.md             # Suite YAML schema and authoring guide
│   ├── architecture.md                # Runtime and comparator pipeline architecture
│   ├── api-reference.md               # Manual Python API reference
│   ├── release-runbook.md             # Manual release workflows and secret matrix
│   └── launch-kit/
│       ├── devto.md                   # dev.to launch article (current-state copy)
│       ├── hn.md                      # Show HN post/title launch pack
│       └── hn-first-comment.md        # HN first-comment launch copy
│
├── src/llm_behavior_diff/             # Main package
│   ├── __init__.py                    # Package initialization
│   ├── schema.py                      # Pydantic models (TestCase, DiffResult, etc.)
│   ├── cli.py                         # Click CLI commands
│   ├── runner.py                      # Suite loader, execution, retries/rate-limit, comparator orchestration
│   ├── aggregator.py                  # Comparator precedence + final category aggregation
│   │
│   ├── adapters/                      # Model provider adapters
│   │   ├── __init__.py
│   │   ├── base.py                    # Abstract ModelAdapter base class
│   │   ├── openai_adapter.py          # OpenAI API implementation
│   │   ├── anthropic_adapter.py       # Anthropic API implementation
│   │   ├── litellm_adapter.py         # LiteLLM-based provider routing adapter
│   │   └── local_adapter.py           # Local OpenAI-compatible adapter
│   │
│   ├── comparators/                   # Behavioral comparison engines
│   │   ├── __init__.py
│   │   ├── base.py                    # Shared comparator result contract + helpers
│   │   ├── semantic.py                # Semantic similarity using embeddings
│   │   ├── behavioral.py              # Deterministic expected-behavior coverage comparator
│   │   ├── factual.py                 # Deterministic factual/hallucination comparator
│   │   ├── format.py                  # Deterministic format/instruction comparator
│   │   └── judge.py                   # Optional LLM-as-judge comparator (metadata-only)
│   │
│   └── reports/                       # Report generation
│       └── __init__.py
│
├── tests/                             # Test suite
│   ├── __init__.py
│   ├── test_schema.py                 # Schema validation tests
│   ├── test_runner.py                 # Runner, resolver, aggregation tests
│   ├── test_cli.py                    # CLI run/compare tests
│   ├── comparators/
│   │   ├── __init__.py
│   │   ├── test_semantic.py           # Semantic comparator tests
│   │   ├── test_behavioral.py         # Behavioral comparator tests
│   │   ├── test_factual.py            # Factual comparator tests
│   │   ├── test_format.py             # Format comparator tests
│   │   └── test_judge.py              # Judge comparator tests
│   └── fixtures/
│       ├── __init__.py
│       └── sample_suite.yaml          # Sample test suite for testing
│
├── suites/                            # Pre-built test suites
│   ├── general_knowledge.yaml         # 10 factual accuracy tests
│   ├── instruction_following.yaml     # 10 instruction compliance tests
│   ├── safety_boundaries.yaml         # 10 refusal/safety boundary tests
│   ├── coding_tasks.yaml              # 10 coding behavior tests
│   └── reasoning.yaml                 # 10 reasoning consistency tests
│
├── .github/
│   └── workflows/
│       ├── ci.yml                     # Core quality CI (master push + PR)
│       ├── release-check.yml          # Build/twine/smoke release readiness check (no publish)
│       ├── publish-pypi.yml           # Manual PyPI/TestPyPI publish workflow
│       ├── docker-image.yml           # Docker build/smoke and optional GHCR push
│       └── model-upgrade-regression.yml # Regression gate for model upgrade runs
│
├── Dockerfile                         # Container image definition
├── Makefile                           # Development commands
├── mkdocs.yml                         # MkDocs site configuration and navigation
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

### src/llm_behavior_diff/adapters/litellm_adapter.py
Concrete implementation for LiteLLM model refs (e.g. `litellm:openai/gpt-4o-mini`)

### src/llm_behavior_diff/adapters/local_adapter.py
Concrete implementation for local OpenAI-compatible endpoints
(`LLM_DIFF_LOCAL_BASE_URL`, optional `LLM_DIFF_LOCAL_API_KEY`)

### src/llm_behavior_diff/comparators/
Comparator modules used by the deterministic Phase 2 pipeline:

- `semantic.py`: embedding-based semantic equivalence check
- `behavioral.py`: expected-behavior coverage deltas
- `factual.py`: factual/current/history-sensitive hallucination/knowledge rules
- `format.py`: structural compliance checks (JSON, markdown table, count, yes/no)
- `judge.py`: optional LLM-as-judge metadata signal (semantic-diff only, non-fatal)
- `base.py`: common `ComparatorResult` contract and helper scoring functions

### src/llm_behavior_diff/aggregator.py
Comparator-first aggregation logic:

- Applies precedence: semantic-same > factual > format > behavioral > unknown
- Produces final category/regression/improvement/confidence/explanation
- Writes comparator decision summaries for report metadata

### src/llm_behavior_diff/cli.py
Click-based CLI with three main commands:

1. `llm-diff run` - Run behavioral diff tests
2. `llm-diff report` - Generate reports (json, html, markdown, table)
3. `llm-diff compare` - Compare two reports

### src/llm_behavior_diff/runner.py
Execution and orchestration engine:

- Loads and validates a single suite YAML
- Resolves model provider from model ids:
  - legacy prefixes (`gpt-/o1-/o3-` => OpenAI, `claude-` => Anthropic)
  - explicit refs (`litellm:<model_ref>`, `local:<model_ref>`)
- Runs test cases concurrently with retry/rate-limit controls
- Executes comparator-first pipeline (semantic + behavioral + factual + format)
- Optionally executes LLM-as-judge on semantic-diff tests (`--judge-model`) without overriding final classification
- Builds aggregated `BehaviorReport` with token/cost/comparator metadata

### pyproject.toml
Python package configuration:

- Entry point: `llm-diff` command
- Dependencies: pydantic, click, rich, openai, anthropic, litellm, sentence-transformers
- Optional dev dependencies for testing and MkDocs documentation
- Build system configuration

### mkdocs.yml
Documentation site configuration:

- Material theme
- Navigation for docs home, references, architecture, and release runbook
- Strict build mode compatibility

### tests/
Test coverage for all modules:

- `test_schema.py`: Validates all Pydantic models
- `test_runner.py`: Tests suite loading, provider resolution, heuristics, and aggregation
- `test_cli.py`: Tests dry-run, run output, and compare output paths
- `test_suites.py`: Validates built-in suite YAML files and dry-run smoke checks
- `test_semantic.py`: Tests semantic comparator
- `sample_suite.yaml`: Example test suite for integration testing

### suites/
Pre-built test suites organized by domain:

- `general_knowledge.yaml`: 10 factual knowledge tests
- `instruction_following.yaml`: 10 instruction compliance tests
- `safety_boundaries.yaml`: 10 refusal and safety-boundary tests
- `coding_tasks.yaml`: 10 coding task tests
- `reasoning.yaml`: 10 multi-step reasoning tests

## Data Flow

```
1. User creates test suite (YAML)
2. CLI loads suite and instantiates adapters
3. Test runner executes tests in parallel:
   - Model A adapter.generate(prompt) → response_a
   - Model B adapter.generate(prompt) → response_b
4. Comparators analyze responses:
   - SemanticComparator: Check semantic equivalence
   - BehavioralComparator: expected-behavior coverage delta
   - FactualComparator: deterministic factual/hallucination rules
   - FormatComparator: deterministic structural constraint checks
   - JudgeComparator (optional): metadata-only A/B/TIE signal on semantic diffs
5. Aggregator combines results into BehaviorReport with fixed precedence
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

**LiteLLM**: `litellm:<model_ref>` (for example `litellm:openai/gpt-4o-mini`)

**Local OpenAI-compatible**: `local:<model_ref>` (for example `local:llama3.1`)

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

1. **Setup**: `make install-dev`
2. **Code**: Write/edit files
3. **Test**: `make test-cov`
4. **Lint**: `make lint`
5. **Format**: `make format`
6. **CI parity check**: `make ci-local`
7. **Release parity check**: `make release-local`
8. **Clean**: `make clean`

## Phases & Feature Roadmap

### Phase 1: Core Engine (Week 1)
- [x] Project setup and structure
- [x] Schema definitions
- [x] Base adapter abstraction
- [x] OpenAI and Anthropic adapters
- [x] Test runner with concurrency
- [x] Cost tracking

### Phase 1.5: Hardening (Current)
- [x] Retry + backoff for transient failures
- [x] Per-model rate limiting
- [x] Continue-on-error mode with error summaries
- [x] Pricing override file support
- [x] Cost deltas in compare output

### Phase 2: Comparators (Week 1-2)
- [x] Semantic comparator (embeddings)
- [x] Behavioral comparator (deterministic coverage delta)
- [x] Factual comparator (deterministic factual rules)
- [x] Format comparator (deterministic structure checks)
- [x] Comparator-first aggregator module
- [x] Optional LLM-as-judge mode (metadata-only)

### Phase 3: Reporting & CLI (Week 2)
- [x] CLI skeleton with commands
- [x] Report generator shell
- [x] JSON reporting implementation
- [x] HTML reporting with visualization (baseline)
- [x] Markdown summary generation (baseline)
- [x] Terminal rich output (baseline)

### Phase 4: Distribution
- [x] GitHub Actions CI
- [x] Docker image
- [x] PyPI packaging
- [x] GitHub Action for model upgrades

### Phase 5: Documentation & Launch
- [x] README
- [x] Quick start guide
- [x] Contributing guidelines
- [x] API reference docs
- [x] Example test suites
- [x] Launch kit (dev.to + HN current-state copy)

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
- `mkdocs>=1.6.0`: Documentation build tool
- `mkdocs-material>=9.5.0`: Documentation theme

## License & Contributing

Licensed under MIT. See LICENSE and CONTRIBUTING.md.

All contributions welcome! Start with an issue or discussion.
