"""Deterministic factual comparator."""

from __future__ import annotations

from ..schema import TestCase
from .base import ComparatorResult, score_confidence_from_delta, score_expected_behavior_coverage

_FACTUAL_HINTS = ("factual", "current", "history", "knowledge")


class FactualComparator:
    """Detect factual shifts using expected-behavior coverage heuristics."""

    def __init__(self, threshold: float = 0.20):
        self.threshold = threshold

    def compare(self, test_case: TestCase, response_a: str, response_b: str) -> ComparatorResult:
        """Return factual change decision."""
        if not self._applies(test_case):
            return ComparatorResult(
                score_a=0.0,
                score_b=0.0,
                delta=0.0,
                applies=False,
                decision="not_applied",
                confidence=0.0,
                reason="Test case is not factual/current/history-weighted.",
            )

        score_a = score_expected_behavior_coverage(test_case.expected_behavior, response_a)
        score_b = score_expected_behavior_coverage(test_case.expected_behavior, response_b)
        delta = score_b - score_a

        if score_a >= 0.65 and score_b <= 0.35:
            decision = "hallucination_new"
            reason = "Strong factual degradation detected in model B."
        elif score_b >= 0.65 and score_a <= 0.35:
            decision = "hallucination_fixed"
            reason = "Strong factual recovery detected in model B."
        elif abs(delta) >= self.threshold:
            decision = "knowledge_change"
            reason = "Meaningful factual/knowledge shift detected."
        else:
            decision = "neutral"
            reason = "No strong factual shift detected."

        return ComparatorResult(
            score_a=score_a,
            score_b=score_b,
            delta=delta,
            applies=True,
            decision=decision,
            confidence=score_confidence_from_delta(delta),
            reason=reason,
        )

    def _applies(self, test_case: TestCase) -> bool:
        """Check whether this test should be treated as factual-sensitive."""
        category = test_case.category.lower()
        tags = " ".join(test_case.tags).lower()
        metadata_text = " ".join(
            [str(key).lower() + str(value).lower() for key, value in test_case.metadata.items()]
        )
        haystack = " ".join([category, tags, metadata_text])
        return any(hint in haystack for hint in _FACTUAL_HINTS)

