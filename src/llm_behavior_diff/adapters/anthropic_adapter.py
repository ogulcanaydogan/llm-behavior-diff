"""
Anthropic API adapter for Claude models.

Supports Claude 3 family (Opus, Sonnet, Haiku) and other Anthropic models.
"""

import time
from typing import Any, Dict, Optional

from .base import ModelAdapter, ModelAdapterConfig


class AnthropicAdapter(ModelAdapter):
    """
    Adapter for Anthropic Claude models.

    Requires ANTHROPIC_API_KEY environment variable or explicit API key.
    """

    def __init__(self, model: str, config: Optional[ModelAdapterConfig] = None):
        """
        Initialize Anthropic adapter.

        Args:
            model: Model name (e.g., 'claude-3-opus', 'claude-3-sonnet', 'claude-3-haiku')
            config: Optional adapter configuration
        """
        super().__init__(model, config)
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ImportError("anthropic package required. Install with: pip install anthropic") from exc

        api_key = self.config.api_key or None  # Uses ANTHROPIC_API_KEY env var by default
        self.client = AsyncAnthropic(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> tuple[str, Dict[str, Any]]:
        """
        Generate response from Anthropic model.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)
            **kwargs: Additional parameters (top_p, top_k, etc.)

        Returns:
            Tuple of (response_text, metadata)
        """
        start_time = time.time()

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
                timeout=self.config.timeout,
                **kwargs,
            )

            latency_ms = (time.time() - start_time) * 1000
            text = response.content[0].text if response.content else ""

            metadata = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
                "latency_ms": latency_ms,
                "stop_reason": response.stop_reason,
                "provider": "anthropic",
            }

            return text, metadata

        except Exception as exc:
            raise RuntimeError(f"Anthropic API error: {str(exc)}") from exc

    async def health_check(self) -> bool:
        """
        Check if Anthropic API is accessible.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            # Test with a simple API call
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}],
            )
            return response.stop_reason is not None
        except Exception:
            return False
