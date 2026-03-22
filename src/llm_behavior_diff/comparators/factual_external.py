"""Optional metadata-only external factual validation comparator."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..connectors.base import FactualConnector, SearchResult
from ..schema import TestCase
from .base import ComparatorResult, score_confidence_from_delta
from .factual import is_factual_applicable

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "also",
    "among",
    "because",
    "before",
    "being",
    "between",
    "both",
    "could",
    "does",
    "doing",
    "during",
    "each",
    "from",
    "have",
    "having",
    "into",
    "just",
    "more",
    "most",
    "other",
    "over",
    "same",
    "such",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "under",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
}


def normalize_query_text(value: str, max_chars: int = 500) -> str:
    """Normalize and trim connector query text."""
    normalized = _WHITESPACE_PATTERN.sub(" ", value).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip()


def extract_evidence_terms(
    results: list[SearchResult], *, max_terms: int = 30, min_token_length: int = 4
) -> list[str]:
    """Extract stable high-signal terms from connector snippets."""
    counts: Counter[str] = Counter()
    for result in results:
        for token in _TOKEN_PATTERN.findall(result.snippet.lower()):
            if len(token) < min_token_length:
                continue
            if token in _STOPWORDS:
                continue
            counts[token] += 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _count in ranked[:max_terms]]


def compute_support_score(response: str, evidence_terms: list[str]) -> tuple[float, list[str]]:
    """Compute support score as matched evidence terms divided by evidence size."""
    if not evidence_terms:
        return 0.0, []

    response_tokens = set(_TOKEN_PATTERN.findall(response.lower()))
    matched = sorted(term for term in evidence_terms if term in response_tokens)
    return len(matched) / len(evidence_terms), matched


class ExternalFactualComparator:
    """Deterministic external factual signal using connector evidence terms."""

    def __init__(
        self,
        connector: FactualConnector,
        *,
        max_results: int = 3,
        timeout_seconds: float = 8.0,
        min_evidence_terms: int = 8,
        delta_threshold: float = 0.15,
        query_max_chars: int = 500,
    ) -> None:
        self.connector = connector
        self.max_results = max_results
        self.timeout_seconds = timeout_seconds
        self.min_evidence_terms = min_evidence_terms
        self.delta_threshold = delta_threshold
        self.query_max_chars = query_max_chars

    async def compare(
        self,
        test_case: TestCase,
        response_a: str,
        response_b: str,
        *,
        is_semantically_same: bool,
    ) -> tuple[ComparatorResult, dict[str, Any]]:
        """Compute metadata-only external factual comparison."""
        metadata: dict[str, Any] = {
            "connector": self.connector.name,
            "enabled": True,
        }

        if is_semantically_same:
            return (
                ComparatorResult(
                    score_a=0.0,
                    score_b=0.0,
                    delta=0.0,
                    applies=False,
                    decision="not_applied",
                    confidence=0.0,
                    reason="External factual check skipped for semantic-same response pair.",
                ),
                metadata,
            )

        if not is_factual_applicable(test_case):
            return (
                ComparatorResult(
                    score_a=0.0,
                    score_b=0.0,
                    delta=0.0,
                    applies=False,
                    decision="not_applied",
                    confidence=0.0,
                    reason="External factual check skipped for non-factual test case.",
                ),
                metadata,
            )

        query = normalize_query_text(
            f"{test_case.prompt} {test_case.expected_behavior}",
            max_chars=self.query_max_chars,
        )
        metadata["query"] = query

        try:
            results = await self.connector.search(
                query=query,
                max_results=self.max_results,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            metadata["error"] = str(exc)
            return (
                ComparatorResult(
                    score_a=0.0,
                    score_b=0.0,
                    delta=0.0,
                    applies=False,
                    decision="external_error",
                    confidence=0.0,
                    reason=f"External factual connector error: {exc}",
                ),
                metadata,
            )

        metadata["results"] = [result.__dict__ for result in results]
        evidence_terms = extract_evidence_terms(results, max_terms=30)
        metadata["evidence_terms"] = evidence_terms

        if len(evidence_terms) < self.min_evidence_terms:
            return (
                ComparatorResult(
                    score_a=0.0,
                    score_b=0.0,
                    delta=0.0,
                    applies=False,
                    decision="unavailable",
                    confidence=0.0,
                    reason="External factual evidence is insufficient for scoring.",
                ),
                metadata,
            )

        score_a, matched_a = compute_support_score(response_a, evidence_terms)
        score_b, matched_b = compute_support_score(response_b, evidence_terms)
        delta = score_b - score_a
        metadata["matched_terms_a"] = matched_a
        metadata["matched_terms_b"] = matched_b

        if delta >= self.delta_threshold:
            decision = "external_recovery"
            reason = "Model B is better supported by external factual evidence."
        elif delta <= -self.delta_threshold:
            decision = "external_degradation"
            reason = "Model B is less supported by external factual evidence."
        else:
            decision = "external_neutral"
            reason = "No strong factual support shift from external evidence."

        return (
            ComparatorResult(
                score_a=score_a,
                score_b=score_b,
                delta=delta,
                applies=True,
                decision=decision,
                confidence=score_confidence_from_delta(delta),
                reason=reason,
            ),
            metadata,
        )
