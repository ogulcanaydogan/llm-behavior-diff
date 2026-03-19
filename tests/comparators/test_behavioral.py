"""Tests for deterministic behavioral comparator."""

import pytest

from llm_behavior_diff.comparators.behavioral import BehavioralComparator
from llm_behavior_diff.schema import TestCase as SuiteCase


def _case(expected_behavior: str, category: str = "reasoning") -> SuiteCase:
    return SuiteCase(
        id="t1",
        prompt="prompt",
        category=category,
        expected_behavior=expected_behavior,
    )


def test_behavioral_improvement_threshold() -> None:
    comparator = BehavioralComparator(threshold=0.20)
    result = comparator.compare(
        test_case=_case("alpha beta gamma"),
        response_a="alpha",
        response_b="alpha beta gamma",
    )

    assert result.applies is True
    assert result.decision == "improvement"
    assert result.delta == pytest.approx(2 / 3)


def test_behavioral_regression_threshold() -> None:
    comparator = BehavioralComparator(threshold=0.20)
    result = comparator.compare(
        test_case=_case("alpha beta gamma"),
        response_a="alpha beta gamma",
        response_b="alpha",
    )

    assert result.applies is True
    assert result.decision == "regression"
    assert result.delta == pytest.approx(-(2 / 3))


def test_behavioral_neutral_within_threshold() -> None:
    comparator = BehavioralComparator(threshold=0.26)
    result = comparator.compare(
        test_case=_case("alpha beta gamma delta"),
        response_a="alpha beta",
        response_b="alpha beta gamma",
    )

    assert result.applies is True
    assert result.decision == "neutral"
    assert result.delta == pytest.approx(0.25)
