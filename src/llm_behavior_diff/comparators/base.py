"""Shared comparator primitives and helpers."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass
class ComparatorResult:
    """Standard comparator output contract."""

    score_a: float
    score_b: float
    delta: float
    applies: bool
    decision: str
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Convert comparator output into a JSON-serializable dictionary."""
        return asdict(self)


def score_expected_behavior_coverage(expected_behavior: str, response: str) -> float:
    """
    Score how much expected behavior text is covered by a model response.

    Score is `overlap(expected_tokens, response_tokens) / expected_tokens`.
    """
    expected_tokens = set(_TOKEN_PATTERN.findall(expected_behavior.lower()))
    if not expected_tokens:
        return 0.0

    response_tokens = set(_TOKEN_PATTERN.findall(response.lower()))
    overlap = expected_tokens.intersection(response_tokens)
    return len(overlap) / len(expected_tokens)


def score_confidence_from_delta(delta: float, minimum: float = 0.5) -> float:
    """Convert score delta magnitude into a normalized confidence value."""
    return min(1.0, max(minimum, abs(delta) + minimum))
