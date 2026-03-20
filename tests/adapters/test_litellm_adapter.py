"""Tests for LiteLLM adapter behavior and metadata normalization."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm_behavior_diff.adapters.litellm_adapter import LiteLLMAdapter


@pytest.mark.asyncio
async def test_litellm_adapter_generate_success_normalizes_usage() -> None:
    adapter = LiteLLMAdapter(model="openai/gpt-4o-mini")
    captured: dict[str, object] = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="hello from litellm"),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
        )

    adapter._acompletion = fake_acompletion
    text, metadata = await adapter.generate("say hello", max_tokens=32, temperature=0.2)

    assert text == "hello from litellm"
    assert metadata["input_tokens"] == 11
    assert metadata["output_tokens"] == 7
    assert metadata["tokens_used"] == 18
    assert metadata["provider"] == "litellm"
    assert captured["model"] == "openai/gpt-4o-mini"
    assert captured["messages"] == [{"role": "user", "content": "say hello"}]


@pytest.mark.asyncio
async def test_litellm_adapter_generate_wraps_errors() -> None:
    adapter = LiteLLMAdapter(model="openai/gpt-4o-mini")

    async def fake_acompletion(**kwargs):
        del kwargs
        raise RuntimeError("boom")

    adapter._acompletion = fake_acompletion
    with pytest.raises(RuntimeError, match="LiteLLM API error"):
        await adapter.generate("hello")


@pytest.mark.asyncio
async def test_litellm_adapter_health_check() -> None:
    adapter = LiteLLMAdapter(model="openai/gpt-4o-mini")

    async def fake_success(**kwargs):
        del kwargs
        return {}

    adapter._acompletion = fake_success
    assert await adapter.health_check() is True

    async def fake_fail(**kwargs):
        del kwargs
        raise RuntimeError("unavailable")

    adapter._acompletion = fake_fail
    assert await adapter.health_check() is False
