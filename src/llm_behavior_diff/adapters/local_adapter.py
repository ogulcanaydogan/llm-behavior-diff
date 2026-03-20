"""
Local OpenAI-compatible adapter.

Targets local gateways that implement OpenAI Chat Completions APIs.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from .base import ModelAdapter, ModelAdapterConfig

DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"
DEFAULT_LOCAL_API_KEY = "local-api-key"


class LocalAdapter(ModelAdapter):
    """
    Adapter for local OpenAI-compatible endpoints.

    Environment variables:
    - LLM_DIFF_LOCAL_BASE_URL (default: http://localhost:11434/v1)
    - LLM_DIFF_LOCAL_API_KEY (optional, default local-api-key placeholder)
    """

    def __init__(self, model: str, config: Optional[ModelAdapterConfig] = None):
        super().__init__(model, config)
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("openai package required. Install with: pip install openai") from exc

        api_key = (
            self.config.api_key or os.getenv("LLM_DIFF_LOCAL_API_KEY") or DEFAULT_LOCAL_API_KEY
        )
        base_url = (
            self.config.base_url or os.getenv("LLM_DIFF_LOCAL_BASE_URL") or DEFAULT_LOCAL_BASE_URL
        )
        self.base_url = base_url
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> tuple[str, Dict[str, Any]]:
        start_time = time.time()
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=self.config.timeout,
                **kwargs,
            )
            latency_ms = (time.time() - start_time) * 1000
            text = response.choices[0].message.content or ""
            prompt_tokens = int(getattr(response.usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(response.usage, "completion_tokens", 0) or 0)
            total_tokens = int(getattr(response.usage, "total_tokens", 0) or 0)
            if total_tokens <= 0:
                total_tokens = prompt_tokens + completion_tokens

            metadata = {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "tokens_used": total_tokens,
                "latency_ms": latency_ms,
                "stop_reason": response.choices[0].finish_reason,
                "provider": "local",
                "base_url": self.base_url,
            }
            return text, metadata
        except Exception as exc:
            raise RuntimeError(f"Local OpenAI-compatible API error: {exc}") from exc

    async def health_check(self) -> bool:
        try:
            await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0,
                timeout=self.config.timeout,
            )
            return True
        except Exception:
            return False
