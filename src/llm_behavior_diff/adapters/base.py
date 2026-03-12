"""
Abstract base class for model adapters.

Defines the interface that all LLM provider adapters must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ModelAdapterConfig:
    """Configuration for a model adapter."""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: int = 60
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelAdapter(ABC):
    """
    Abstract base class for LLM model adapters.

    Provides unified interface for querying different LLM providers
    (OpenAI, Anthropic, LiteLLM, local models, etc.)
    """

    def __init__(self, model: str, config: Optional[ModelAdapterConfig] = None):
        """
        Initialize adapter.

        Args:
            model: Model name/version identifier
            config: Optional adapter configuration
        """
        self.model = model
        self.config = config or ModelAdapterConfig()

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> tuple[str, Dict[str, Any]]:
        """
        Generate model response.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters

        Returns:
            Tuple of (response_text, metadata)
            Metadata includes: tokens_used, latency_ms, stop_reason, etc.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if model is accessible.

        Returns:
            True if model is available, False otherwise
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model})"
