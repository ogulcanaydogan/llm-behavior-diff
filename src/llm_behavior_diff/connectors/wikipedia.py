"""Wikipedia connector for external factual evidence lookups."""

from __future__ import annotations

import re
from urllib.parse import quote

import httpx

from .base import SearchResult

_SEARCH_ENDPOINT = "https://en.wikipedia.org/w/api.php"
_SUMMARY_ENDPOINT = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_TAG_PATTERN = re.compile(r"<[^>]+>")
_SPACE_PATTERN = re.compile(r"\s+")


def _clean_text(value: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    without_tags = _TAG_PATTERN.sub(" ", value)
    return _SPACE_PATTERN.sub(" ", without_tags).strip()


class WikipediaConnector:
    """Fetch factual evidence snippets from Wikipedia search + page summaries."""

    name = "wikipedia"

    async def search(self, query: str, max_results: int, timeout: float) -> list[SearchResult]:
        """Search Wikipedia and return normalized records."""
        if max_results < 1:
            return []

        params: dict[str, str | int] = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": max_results,
            "format": "json",
            "utf8": 1,
        }
        headers = {"User-Agent": "llm-behavior-diff/0.1 factual-connector"}

        async with httpx.AsyncClient(
            timeout=timeout, headers=headers, follow_redirects=True
        ) as client:
            search_response = await client.get(_SEARCH_ENDPOINT, params=params)
            search_response.raise_for_status()
            search_payload = search_response.json()

            query_payload = search_payload.get("query", {})
            search_rows = query_payload.get("search", [])
            if not isinstance(search_rows, list):
                return []

            results: list[SearchResult] = []
            for item in search_rows:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "")).strip()
                if not title:
                    continue

                fallback_snippet = _clean_text(str(item.get("snippet", "")))
                summary_text, summary_url = await self._fetch_page_summary(
                    client=client,
                    title=title,
                    fallback_snippet=fallback_snippet,
                )
                results.append(
                    SearchResult(
                        title=title,
                        url=summary_url,
                        snippet=summary_text,
                    )
                )

            return results[:max_results]

    async def _fetch_page_summary(
        self,
        *,
        client: httpx.AsyncClient,
        title: str,
        fallback_snippet: str,
    ) -> tuple[str, str]:
        """Return summary text and canonical URL for one Wikipedia page."""
        encoded_title = quote(title.replace(" ", "_"), safe="_")
        default_url = f"https://en.wikipedia.org/wiki/{encoded_title}"
        endpoint = _SUMMARY_ENDPOINT.format(title=encoded_title)

        try:
            response = await client.get(endpoint)
            response.raise_for_status()
        except httpx.HTTPError:
            return fallback_snippet, default_url

        payload = response.json()
        if not isinstance(payload, dict):
            return fallback_snippet, default_url

        summary = _clean_text(str(payload.get("extract", ""))) or fallback_snippet
        content_urls = payload.get("content_urls", {})
        if not isinstance(content_urls, dict):
            return summary, default_url
        desktop = content_urls.get("desktop", {})
        if not isinstance(desktop, dict):
            return summary, default_url
        page_url = str(desktop.get("page", "")).strip() or default_url
        return summary, page_url
