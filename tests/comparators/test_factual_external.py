"""Tests for optional external factual comparator and Wikipedia connector."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from llm_behavior_diff.comparators.factual_external import (
    ExternalFactualComparator,
    compute_support_score,
    extract_evidence_terms,
    normalize_query_text,
)
from llm_behavior_diff.connectors.base import SearchResult
from llm_behavior_diff.connectors.wikipedia import WikipediaConnector
from llm_behavior_diff.schema import TestCase as SuiteCase


class StubConnector:
    """Simple factual connector stub for deterministic unit tests."""

    name = "stub"

    def __init__(
        self, results: list[SearchResult] | None = None, error: Exception | None = None
    ) -> None:
        self.results = results or []
        self.error = error

    async def search(self, query: str, max_results: int, timeout: float) -> list[SearchResult]:
        del query, max_results, timeout
        if self.error is not None:
            raise self.error
        return self.results


def _factual_case() -> SuiteCase:
    return SuiteCase(
        id="t1",
        prompt="Who discovered penicillin?",
        category="factual_knowledge",
        tags=["history"],
        expected_behavior="mention Alexander Fleming and 1928 discovery context",
    )


def _request(url: str, params: dict[str, Any] | None = None) -> httpx.Request:
    return httpx.Request("GET", url, params=params)


@pytest.mark.asyncio
async def test_wikipedia_connector_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, url: str, params: dict[str, Any] | None = None, **kwargs: Any):
        del self, kwargs
        request = _request(url, params=params)
        if "w/api.php" in url:
            return httpx.Response(
                200,
                request=request,
                json={
                    "query": {
                        "search": [
                            {
                                "title": "Alexander Fleming",
                                "snippet": "<b>Alexander</b> Fleming scientist",
                            },
                            {"title": "Penicillin", "snippet": "Penicillin antibiotic"},
                        ]
                    }
                },
            )
        if "summary/Alexander_Fleming" in url:
            return httpx.Response(
                200,
                request=request,
                json={
                    "extract": "Alexander Fleming discovered penicillin in 1928.",
                    "content_urls": {
                        "desktop": {"page": "https://en.wikipedia.org/wiki/Alexander_Fleming"}
                    },
                },
            )
        if "summary/Penicillin" in url:
            return httpx.Response(
                200,
                request=request,
                json={
                    "extract": "Penicillin is a group of antibiotics discovered from Penicillium molds.",
                    "content_urls": {
                        "desktop": {"page": "https://en.wikipedia.org/wiki/Penicillin"}
                    },
                },
            )
        return httpx.Response(404, request=request, json={})

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    connector = WikipediaConnector()
    results = await connector.search("penicillin discovery", max_results=2, timeout=2.0)

    assert len(results) == 2
    assert results[0].title == "Alexander Fleming"
    assert "discovered penicillin" in results[0].snippet.lower()
    assert results[0].url == "https://en.wikipedia.org/wiki/Alexander_Fleming"


@pytest.mark.asyncio
async def test_wikipedia_connector_empty_search_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, url: str, params: dict[str, Any] | None = None, **kwargs: Any):
        del self, kwargs
        request = _request(url, params=params)
        return httpx.Response(200, request=request, json={"query": {"search": []}})

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    connector = WikipediaConnector()
    results = await connector.search("something", max_results=3, timeout=2.0)
    assert results == []


@pytest.mark.asyncio
async def test_wikipedia_connector_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, url: str, params: dict[str, Any] | None = None, **kwargs: Any):
        del self, kwargs
        request = _request(url, params=params)
        return httpx.Response(500, request=request, text="server error")

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    connector = WikipediaConnector()
    with pytest.raises(httpx.HTTPStatusError):
        await connector.search("test", max_results=1, timeout=1.0)


@pytest.mark.asyncio
async def test_wikipedia_connector_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, url: str, params: dict[str, Any] | None = None, **kwargs: Any):
        del self, kwargs
        request = _request(url, params=params)
        raise httpx.ReadTimeout("timeout", request=request)

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    connector = WikipediaConnector()
    with pytest.raises(httpx.ReadTimeout):
        await connector.search("test", max_results=1, timeout=1.0)


def test_evidence_term_extraction_and_support_score_are_deterministic() -> None:
    results = [
        SearchResult(
            title="A",
            url="https://example.com/a",
            snippet="Alexander Fleming discovered penicillin in 1928 in London.",
        ),
        SearchResult(
            title="B",
            url="https://example.com/b",
            snippet="Penicillin discovery is credited to Alexander Fleming.",
        ),
    ]
    terms = extract_evidence_terms(results, max_terms=10)
    assert "alexander" in terms
    assert "fleming" in terms
    assert "penicillin" in terms

    score, matched = compute_support_score(
        "Alexander Fleming discovered penicillin and transformed antibiotic medicine.", terms
    )
    assert score > 0.0
    assert matched == sorted(matched)


@pytest.mark.asyncio
async def test_external_factual_comparator_recovery_and_degradation_thresholds() -> None:
    comparator = ExternalFactualComparator(
        connector=StubConnector(
            results=[
                SearchResult(
                    title="Fleming",
                    url="https://example.com",
                    snippet="alexander fleming discovered penicillin antibiotic discovery 1928 london lab",
                ),
                SearchResult(
                    title="Penicillin",
                    url="https://example.com",
                    snippet="penicillin discovery fleming mold antibiotic clinical history medicine",
                ),
            ]
        ),
        min_evidence_terms=8,
        delta_threshold=0.15,
    )

    factual_case = _factual_case()
    recovery, _ = await comparator.compare(
        factual_case,
        response_a="This was discovered by a random person.",
        response_b="Alexander Fleming discovered penicillin in 1928.",
        is_semantically_same=False,
    )
    assert recovery.decision == "external_recovery"
    assert recovery.applies is True
    assert recovery.delta >= 0.15

    degradation, _ = await comparator.compare(
        factual_case,
        response_a="Alexander Fleming discovered penicillin in 1928.",
        response_b="Unknown person discovered an unrelated thing.",
        is_semantically_same=False,
    )
    assert degradation.decision == "external_degradation"
    assert degradation.applies is True
    assert degradation.delta <= -0.15


@pytest.mark.asyncio
async def test_external_factual_comparator_unavailable_and_error() -> None:
    unavailable_comparator = ExternalFactualComparator(
        connector=StubConnector(
            results=[
                SearchResult(title="A", url="https://example.com", snippet="short snippet only"),
            ]
        ),
        min_evidence_terms=8,
    )
    unavailable_result, unavailable_meta = await unavailable_comparator.compare(
        _factual_case(),
        response_a="text a",
        response_b="text b",
        is_semantically_same=False,
    )
    assert unavailable_result.decision == "unavailable"
    assert unavailable_result.applies is False
    assert "evidence_terms" in unavailable_meta

    error_comparator = ExternalFactualComparator(
        connector=StubConnector(error=RuntimeError("connector failed")),
        min_evidence_terms=8,
    )
    error_result, error_meta = await error_comparator.compare(
        _factual_case(),
        response_a="text a",
        response_b="text b",
        is_semantically_same=False,
    )
    assert error_result.decision == "external_error"
    assert error_result.applies is False
    assert "connector failed" in str(error_meta.get("error", ""))


def test_normalize_query_text_truncates_and_collapses_whitespace() -> None:
    raw = "This   is\n\n  a   very long query"
    normalized = normalize_query_text(raw, max_chars=10)
    assert normalized == "This is a"
