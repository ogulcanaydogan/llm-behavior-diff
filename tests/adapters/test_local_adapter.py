"""Tests for local OpenAI-compatible adapter behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm_behavior_diff.adapters.local_adapter import (
    DEFAULT_LOCAL_API_KEY,
    DEFAULT_LOCAL_BASE_URL,
    LocalAdapter,
)


class _FakeCompletions:
    def __init__(self, response, should_fail: bool = False) -> None:
        self.response = response
        self.should_fail = should_fail

    async def create(self, **kwargs):
        del kwargs
        if self.should_fail:
            raise RuntimeError("gateway unavailable")
        return self.response


class _FakeClient:
    def __init__(self, *, api_key: str, base_url: str, response, should_fail: bool = False) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.chat = SimpleNamespace(
            completions=_FakeCompletions(response=response, should_fail=should_fail)
        )


@pytest.mark.asyncio
async def test_local_adapter_uses_env_fallback_and_normalizes_usage(monkeypatch) -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="local ok"), finish_reason="stop")
        ],
        usage=SimpleNamespace(prompt_tokens=9, completion_tokens=4, total_tokens=13),
    )
    captured: dict[str, str] = {}

    def fake_async_openai(*, api_key: str, base_url: str):
        captured["api_key"] = api_key
        captured["base_url"] = base_url
        return _FakeClient(api_key=api_key, base_url=base_url, response=response)

    monkeypatch.setenv("LLM_DIFF_LOCAL_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LLM_DIFF_LOCAL_API_KEY", "test-local-key")
    monkeypatch.setattr("openai.AsyncOpenAI", fake_async_openai)

    adapter = LocalAdapter(model="llama3.1")
    text, metadata = await adapter.generate("ping", max_tokens=20, temperature=0.0)

    assert captured["base_url"] == "http://127.0.0.1:8000/v1"
    assert captured["api_key"] == "test-local-key"
    assert text == "local ok"
    assert metadata["input_tokens"] == 9
    assert metadata["output_tokens"] == 4
    assert metadata["tokens_used"] == 13
    assert metadata["provider"] == "local"
    assert metadata["base_url"] == "http://127.0.0.1:8000/v1"


@pytest.mark.asyncio
async def test_local_adapter_defaults_when_env_missing(monkeypatch) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    captured: dict[str, str] = {}

    def fake_async_openai(*, api_key: str, base_url: str):
        captured["api_key"] = api_key
        captured["base_url"] = base_url
        return _FakeClient(api_key=api_key, base_url=base_url, response=response)

    monkeypatch.delenv("LLM_DIFF_LOCAL_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_DIFF_LOCAL_API_KEY", raising=False)
    monkeypatch.setattr("openai.AsyncOpenAI", fake_async_openai)

    adapter = LocalAdapter(model="llama3.1")
    await adapter.generate("ping")

    assert captured["base_url"] == DEFAULT_LOCAL_BASE_URL
    assert captured["api_key"] == DEFAULT_LOCAL_API_KEY


@pytest.mark.asyncio
async def test_local_adapter_wraps_errors_and_health_check(monkeypatch) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )

    def fake_async_openai(*, api_key: str, base_url: str):
        return _FakeClient(api_key=api_key, base_url=base_url, response=response, should_fail=True)

    monkeypatch.setattr("openai.AsyncOpenAI", fake_async_openai)
    adapter = LocalAdapter(model="llama3.1")

    with pytest.raises(RuntimeError, match="Local OpenAI-compatible API error"):
        await adapter.generate("ping")
    assert await adapter.health_check() is False
