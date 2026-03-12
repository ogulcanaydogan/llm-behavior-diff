# Contributing to llm-behavior-diff

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

Be respectful, inclusive, and professional. We're building this together.

## Getting Started

### Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/llm-behavior-diff.git
cd llm-behavior-diff
```

### Setup Development Environment

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/ -v --cov=src/llm_behavior_diff
```

### Code Style

We use `black`, `ruff`, and `mypy` for code quality.

```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

Before committing, run:

```bash
make check  # runs black, ruff, mypy, pytest
```

## What to Contribute

### High-Impact Areas

1. **Comparators** (`src/llm_behavior_diff/comparators/`)
   - Behavioral comparator with LLM-as-judge
   - Factual accuracy detection
   - Format/structure drift detection

2. **Model Adapters** (`src/llm_behavior_diff/adapters/`)
   - New provider adapters (Cohere, Together, HuggingFace, etc.)
   - Local model support (Ollama, vLLM)

3. **Test Suites** (`suites/`)
   - Safety boundaries tests
   - Coding tasks tests
   - Reasoning tests
   - Domain-specific tests

4. **Reporting** (`src/llm_behavior_diff/reports/`)
   - PDF reports
   - GitHub PR integration
   - Slack notifications

5. **Documentation**
   - Real-world examples
   - Detailed API docs
   - Integration guides

### Good First Issues

Look for issues labeled `good-first-issue` in GitHub Issues. These are well-scoped tasks perfect for new contributors.

## Development Workflow

### 1. Create Feature Branch

```bash
git checkout -b feature/your-feature-name
```

Use descriptive branch names:
- `feature/llm-as-judge-comparator`
- `fix/semantic-similarity-edge-case`
- `docs/anthropic-adapter-guide`

### 2. Make Changes

Write clean, well-documented code:

```python
def compare(self, text_a: str, text_b: str) -> tuple[float, bool]:
    """
    Compare semantic similarity between two texts.

    Args:
        text_a: First text
        text_b: Second text

    Returns:
        Tuple of (similarity_score, are_semantically_same)
        Similarity score is 0-1, are_semantically_same is True if >= threshold
    """
```

### 3. Write Tests

All new code requires tests:

```python
# tests/comparators/test_semantic.py
def test_semantic_comparator_exact_match():
    comparator = SemanticComparator()
    similarity, is_same = comparator.compare("hello world", "hello world")
    assert similarity == 1.0
    assert is_same is True

def test_semantic_comparator_similar():
    comparator = SemanticComparator()
    similarity, is_same = comparator.compare(
        "The cat is sleeping",
        "A cat is napping"
    )
    assert similarity > 0.8
    assert is_same is True
```

### 4. Run Tests and Linters

```bash
pytest tests/ -v --cov=src/llm_behavior_diff
black src/ tests/
ruff check src/ tests/
mypy src/
```

### 5. Commit

Write clear commit messages:

```
feat: implement llm-as-judge behavioral comparator

- Add LLMJudgeComparator class
- Support OpenAI and Anthropic judges
- Add caching for judge evaluations
- Include 10 unit tests

Closes #42
```

### 6. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Visit GitHub and create a pull request with:
- Clear description of changes
- Reference to related issues
- Test coverage information

## Pull Request Guidelines

### Before Submitting

- [ ] Code follows style guidelines (black, ruff, mypy)
- [ ] All tests pass
- [ ] New code has tests (>80% coverage)
- [ ] Documentation is updated
- [ ] Commit messages are clear
- [ ] No unrelated changes in same PR

### PR Template

```markdown
## Description
Brief description of what this PR does.

## Type
- [ ] Bug fix
- [ ] Feature
- [ ] Documentation
- [ ] Refactor

## Related Issues
Closes #123

## Changes
- Change 1
- Change 2
- Change 3

## Testing
Describe how you tested these changes.

## Checklist
- [ ] Code follows style guidelines
- [ ] All tests pass
- [ ] New tests added (if applicable)
- [ ] Documentation updated
```

## Documentation

### Code Documentation

Use docstrings for all public functions and classes:

```python
def generate(
    self,
    prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    **kwargs: Any,
) -> tuple[str, Dict[str, Any]]:
    """
    Generate model response.

    Args:
        prompt: Input prompt
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        **kwargs: Provider-specific parameters

    Returns:
        Tuple of (response_text, metadata)
        Metadata includes: tokens_used, latency_ms, stop_reason, etc.

    Raises:
        RuntimeError: If API call fails
    """
```

### User Documentation

Update README.md and docs/ for user-facing changes.

## Adding New Comparators

1. Create new file in `src/llm_behavior_diff/comparators/`
2. Inherit from `BaseComparator` (to be defined)
3. Implement required methods
4. Add to `__init__.py`
5. Add tests
6. Document in README

Example:

```python
# src/llm_behavior_diff/comparators/custom.py
class CustomComparator:
    """Custom behavioral comparison logic."""

    def compare(self, text_a: str, text_b: str) -> tuple[float, bool]:
        """Compare texts and return (score, is_same)."""
        pass
```

## Adding New Model Adapters

1. Create new file in `src/llm_behavior_diff/adapters/`
2. Inherit from `ModelAdapter`
3. Implement `generate()` and `health_check()`
4. Add to `__init__.py`
5. Add tests
6. Update README with usage

Example:

```python
# src/llm_behavior_diff/adapters/cohere_adapter.py
class CohereAdapter(ModelAdapter):
    async def generate(self, prompt: str, max_tokens: int, **kwargs):
        """Generate from Cohere API."""
        pass

    async def health_check(self) -> bool:
        """Check Cohere API availability."""
        pass
```

## Issues and Discussions

- Report bugs with reproduction steps
- Suggest features with use cases
- Ask questions in Discussions
- Share research and ideas

## Release Process

Releases are created monthly. Contributors who provide merged PRs are credited.

```bash
# Version bumping (maintainers only)
bumped patch version in pyproject.toml
git tag v0.2.0
git push origin v0.2.0
```

## License

By contributing, you agree that your contributions are licensed under the MIT License.

## Questions?

- Open an issue on GitHub
- Start a Discussion
- Check existing issues/PRs

Thank you for contributing to llm-behavior-diff!
