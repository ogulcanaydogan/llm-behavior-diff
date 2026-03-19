"""
Model adapters for querying different LLM providers.

Provides unified interface for OpenAI and Anthropic adapters.
LiteLLM/local adapters are planned.
"""

from .anthropic_adapter import AnthropicAdapter
from .base import ModelAdapter, ModelAdapterConfig
from .openai_adapter import OpenAIAdapter

__all__ = [
    "ModelAdapter",
    "ModelAdapterConfig",
    "OpenAIAdapter",
    "AnthropicAdapter",
]
