"""Connector primitives for optional external factual validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    """Single external search record used for factual evidence."""

    title: str
    url: str
    snippet: str


class FactualConnector(Protocol):
    """Protocol for external factual evidence providers."""

    name: str

    async def search(self, query: str, max_results: int, timeout: float) -> list[SearchResult]:
        """Search external source and return normalized evidence records."""
        ...
