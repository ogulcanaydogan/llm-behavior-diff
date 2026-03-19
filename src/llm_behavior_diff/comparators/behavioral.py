"""Deterministic behavioral comparator."""

from __future__ import annotations

from ..schema import TestCase
from .base import ComparatorResult, score_confidence_from_delta, score_expected_behavior_coverage


class BehavioralComparator:
    """Compare responses against expected behavior coverage."""

    def __init__(self, threshold: float = 0.20):
        self.threshold = threshold

    def compare(self, test_case: TestCase, response_a: str, response_b: str) -> ComparatorResult:
        """Return behavioral delta and a deterministic decision."""
        score_a = score_expected_behavior_coverage(test_case.expected_behavior, response_a)
        score_b = score_expected_behavior_coverage(test_case.expected_behavior, response_b)
        delta = score_b - score_a

        if delta >= self.threshold:
            decision = "improvement"
            reason = f"Model B expected-behavior coverage improved by {delta:.2f}."
        elif delta <= -self.threshold:
            decision = "regression"
            reason = f"Model B expected-behavior coverage regressed by {abs(delta):.2f}."
        else:
            decision = "neutral"
            reason = "Behavioral delta is below deterministic threshold."

        return ComparatorResult(
            score_a=score_a,
            score_b=score_b,
            delta=delta,
            applies=True,
            decision=decision,
            confidence=score_confidence_from_delta(delta),
            reason=reason,
        )

