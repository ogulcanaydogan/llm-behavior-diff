"""
LiteLLM adapter for provider-agnostic model routing.

Supports model refs like ``openai/gpt-4o-mini`` and other LiteLLM-supported targets.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Tuple

from .base import ModelAdapter, ModelAdapterConfig


def _usage_value(usage: Any, key: str) -> int:
    """Safely extract a numeric usage field from dict/object payloads."""
    if usage is None:
        return 0
    if isinstance(usage, dict):
        value = usage.get(key, 0)
    else:
        value = getattr(usage, key, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _extract_text_and_stop_reason(response: Any) -> Tuple[str, str | None]:
    """Extract text and stop reason from LiteLLM response-like objects."""
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return "", None

    first = choices[0]
    message = getattr(first, "message", None)
    if message is None and isinstance(first, dict):
        message = first.get("message")

    text = ""
    if isinstance(message, dict):
        text = str(message.get("content", "") or "")
    else:
        text = str(getattr(message, "content", "") or "")

    stop_reason = getattr(first, "finish_reason", None)
    if stop_reason is None and isinstance(first, dict):
        stop_reason = first.get("finish_reason")

    return text, stop_reason


class LiteLLMAdapter(ModelAdapter):
    """Adapter that delegates completions to LiteLLM."""

    def __init__(self, model: str, config: ModelAdapterConfig | None = None):
        super().__init__(model, config)
        try:
            from litellm import acompletion
        except ImportError as exc:
            raise ImportError(
                "litellm package required. Install with: pip install litellm"
            ) from exc
        self._acompletion = acompletion

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> tuple[str, Dict[str, Any]]:
        start_time = time.time()
        try:
            response = await self._acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=self.config.timeout,
                **kwargs,
            )
            latency_ms = (time.time() - start_time) * 1000
            text, stop_reason = _extract_text_and_stop_reason(response)
            usage = getattr(response, "usage", None)
            if usage is None and isinstance(response, dict):
                usage = response.get("usage")

            prompt_tokens = _usage_value(usage, "prompt_tokens")
            completion_tokens = _usage_value(usage, "completion_tokens")
            total_tokens = _usage_value(usage, "total_tokens")
            if total_tokens <= 0:
                total_tokens = prompt_tokens + completion_tokens

            metadata = {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "tokens_used": total_tokens,
                "latency_ms": latency_ms,
                "stop_reason": stop_reason,
                "provider": "litellm",
            }
            return text, metadata
        except Exception as exc:
            raise RuntimeError(f"LiteLLM API error: {exc}") from exc

    async def health_check(self) -> bool:
        try:
            await self._acompletion(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0,
                timeout=self.config.timeout,
            )
            return True
        except Exception:
            return False
