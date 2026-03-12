"""
Model adapters for querying different LLM providers.

Provides unified interface for OpenAI, Anthropic, LiteLLM, and local models.
"""

from .base import ModelAdapter, ModelAdapterConfig

__all__ = [
    "ModelAdapter",
    "ModelAdapterConfig",
]
