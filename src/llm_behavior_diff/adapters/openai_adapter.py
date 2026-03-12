"""
OpenAI API adapter for GPT models.

Supports GPT-4o, GPT-4.5, GPT-4, GPT-3.5-turbo, and other OpenAI models.
"""

import time
from typing import Any, Dict, Optional

from .base import ModelAdapter, ModelAdapterConfig


class OpenAIAdapter(ModelAdapter):
    """
    Adapter for OpenAI API models.

    Requires OPENAI_API_KEY environment variable or explicit API key.
    """

    def __init__(self, model: str, config: Optional[ModelAdapterConfig] = None):
        """
        Initialize OpenAI adapter.

        Args:
            model: Model name (e.g., 'gpt-4o', 'gpt-4.5', 'gpt-4-turbo')
            config: Optional adapter configuration
        """
        super().__init__(model, config)
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")

        api_key = self.config.api_key or None  # Uses OPENAI_API_KEY env var by default
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> tuple[str, Dict[str, Any]]:
        """
        Generate response from OpenAI model.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-2)
            **kwargs: Additional parameters (top_p, frequency_penalty, etc.)

        Returns:
            Tuple of (response_text, metadata)
        """
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

            metadata = {
                "tokens_used": response.usage.total_tokens,
                "latency_ms": latency_ms,
                "stop_reason": response.choices[0].finish_reason,
                "provider": "openai",
            }

            return text, metadata

        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}")

    async def health_check(self) -> bool:
        """
        Check if OpenAI API is accessible.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            response = await self.client.models.retrieve(self.model)
            return response.id == self.model
        except Exception:
            return False
