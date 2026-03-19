"""Deterministic format/instruction compliance comparator."""

from __future__ import annotations

import json
import re

from ..schema import TestCase
from .base import ComparatorResult, score_confidence_from_delta


class FormatComparator:
    """Check structural instruction compliance and detect format drift."""

    _sentence_count_pattern = re.compile(r"exactly\s+(\d+)\s+sentences?", re.IGNORECASE)
    _word_count_pattern = re.compile(r"exactly\s+(\d+)\s+words?", re.IGNORECASE)
    _count_pattern = re.compile(
        r"(?:exactly|top)\s+(\d+)\s+(?:items?|ways?|frameworks?|records?)",
        re.IGNORECASE,
    )
    _yes_no_pattern = re.compile(
        r"(answer|respond)\s+only\s+with\s+['\"]?yes['\"]?\s+or\s+['\"]?no['\"]?",
        re.IGNORECASE,
    )

    def __init__(self, threshold: float = 0.20):
        self.threshold = threshold

    def compare(self, test_case: TestCase, response_a: str, response_b: str) -> ComparatorResult:
        """Return deterministic format compliance deltas."""
        constraints = self._extract_constraints(test_case)
        if not constraints:
            return ComparatorResult(
                score_a=0.0,
                score_b=0.0,
                delta=0.0,
                applies=False,
                decision="not_applied",
                confidence=0.0,
                reason="No structural format constraints detected.",
            )

        score_a = self._score_constraints(constraints, response_a)
        score_b = self._score_constraints(constraints, response_b)
        delta = score_b - score_a

        if delta >= self.threshold:
            decision = "instruction_following"
            reason = "Model B satisfies more structural constraints."
        elif delta <= -self.threshold:
            decision = "format_change"
            reason = "Model B violates more structural constraints."
        else:
            decision = "neutral"
            reason = "No meaningful structural compliance difference."

        return ComparatorResult(
            score_a=score_a,
            score_b=score_b,
            delta=delta,
            applies=True,
            decision=decision,
            confidence=score_confidence_from_delta(delta),
            reason=reason,
        )

    def _extract_constraints(self, test_case: TestCase) -> list[tuple[str, int | bool | None]]:
        text = f"{test_case.prompt}\n{test_case.expected_behavior}".lower()
        constraints: list[tuple[str, int | bool | None]] = []

        if "json" in text:
            constraints.append(("valid_json", True))
        if "markdown table" in text or ("table" in text and "columns" in text):
            constraints.append(("markdown_table", True))

        sentence_match = self._sentence_count_pattern.search(text)
        if sentence_match:
            constraints.append(("sentence_count", int(sentence_match.group(1))))

        word_match = self._word_count_pattern.search(text)
        if word_match:
            constraints.append(("word_count", int(word_match.group(1))))

        count_match = self._count_pattern.search(text)
        if count_match:
            constraints.append(("list_count", int(count_match.group(1))))

        if self._yes_no_pattern.search(text):
            constraints.append(("yes_no_only", True))

        return constraints

    def _score_constraints(
        self, constraints: list[tuple[str, int | bool | None]], response: str
    ) -> float:
        if not constraints:
            return 0.0

        satisfied = sum(1 for constraint, value in constraints if self._check(constraint, value, response))
        return satisfied / len(constraints)

    def _check(self, constraint: str, value: int | bool | None, response: str) -> bool:
        normalized = response.strip()
        lowered = normalized.lower()

        if constraint == "valid_json":
            if normalized.startswith("```") and normalized.endswith("```"):
                stripped = normalized.strip("`")
                stripped = stripped.replace("json", "", 1).strip()
            else:
                stripped = normalized
            try:
                json.loads(stripped)
                return True
            except Exception:
                return False

        if constraint == "markdown_table":
            lines = [line for line in normalized.splitlines() if "|" in line]
            if len(lines) < 2:
                return False
            separator = lines[1].replace(" ", "")
            return "---" in separator and "|" in separator

        if constraint == "sentence_count" and isinstance(value, int):
            sentences = [chunk for chunk in re.split(r"[.!?]+", normalized) if chunk.strip()]
            return len(sentences) == value

        if constraint == "word_count" and isinstance(value, int):
            words = re.findall(r"\b[\w'-]+\b", normalized)
            return len(words) == value

        if constraint == "list_count" and isinstance(value, int):
            numbered = len(re.findall(r"^\s*\d+[\.\)]\s+", normalized, flags=re.MULTILINE))
            bullets = len(re.findall(r"^\s*[-*]\s+", normalized, flags=re.MULTILINE))
            comma_items = len([part for part in normalized.split(",") if part.strip()])
            return numbered == value or bullets == value or comma_items == value

        if constraint == "yes_no_only":
            return lowered in {"yes", "no"}

        return False

