"""
Model adapters for querying different LLM providers.

Provides unified interface for OpenAI, Anthropic, LiteLLM, and local adapters.
"""

from .anthropic_adapter import AnthropicAdapter
from .base import ModelAdapter, ModelAdapterConfig
from .litellm_adapter import LiteLLMAdapter
from .local_adapter import LocalAdapter
from .openai_adapter import OpenAIAdapter

__all__ = [
    "ModelAdapter",
    "ModelAdapterConfig",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "LiteLLMAdapter",
    "LocalAdapter",
]
