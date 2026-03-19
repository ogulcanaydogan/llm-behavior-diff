"""Tests for deterministic factual comparator."""

import pytest

from llm_behavior_diff.comparators.factual import FactualComparator
from llm_behavior_diff.schema import TestCase as SuiteCase


def _case(
    *,
    category: str = "factual_knowledge",
    tags: list[str] | None = None,
    metadata: dict | None = None,
    expected_behavior: str = "alpha beta gamma",
) -> SuiteCase:
    return SuiteCase(
        id="t1",
        prompt="prompt",
        category=category,
        tags=tags or [],
        expected_behavior=expected_behavior,
        metadata=metadata or {},
    )


def test_factual_not_applied_for_non_factual_case() -> None:
    comparator = FactualComparator()
    result = comparator.compare(
        test_case=_case(category="reasoning"),
        response_a="alpha beta",
        response_b="alpha",
    )

    assert result.applies is False
    assert result.decision == "not_applied"


def test_factual_hallucination_new() -> None:
    comparator = FactualComparator()
    result = comparator.compare(
        test_case=_case(),
        response_a="alpha beta",
        response_b="alpha",
    )

    assert result.applies is True
    assert result.score_a == pytest.approx(2 / 3)
    assert result.score_b == pytest.approx(1 / 3)
    assert result.decision == "hallucination_new"


def test_factual_hallucination_fixed() -> None:
    comparator = FactualComparator()
    result = comparator.compare(
        test_case=_case(),
        response_a="alpha",
        response_b="alpha beta",
    )

    assert result.applies is True
    assert result.decision == "hallucination_fixed"


def test_factual_knowledge_change_threshold() -> None:
    comparator = FactualComparator(threshold=0.20)
    result = comparator.compare(
        test_case=_case(expected_behavior="alpha beta gamma delta"),
        response_a="alpha beta",
        response_b="alpha beta gamma",
    )

    assert result.applies is True
    assert result.delta == pytest.approx(0.25)
    assert result.decision == "knowledge_change"


def test_factual_neutral_small_delta() -> None:
    comparator = FactualComparator(threshold=0.30)
    result = comparator.compare(
        test_case=_case(expected_behavior="alpha beta gamma delta"),
        response_a="alpha beta",
        response_b="alpha beta gamma",
    )

    assert result.applies is True
    assert result.delta == pytest.approx(0.25)
    assert result.decision == "neutral"
