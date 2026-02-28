"""LLM Provider abstraction layer.

This module provides an abstraction layer for different LLM providers,
allowing the AI agent to work with multiple backends (OpenAI, FlexPal, etc.)
through a common interface.
"""

from app.ai_agent.providers.base import LLMProvider

__all__ = ["LLMProvider"]
