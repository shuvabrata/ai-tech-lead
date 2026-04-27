"""Factory for creating LLM provider instances.

This module provides a factory function to instantiate the appropriate
LLM provider based on configuration.
"""

import os
from typing import Optional, Dict

from dotenv import load_dotenv

from app.ai_agent.providers.base import LLMProvider
from app.ai_agent.providers.openai import OpenAIProvider
from app.common.logger import logger

# Load environment variables
load_dotenv()

# Provider instance cache (singleton pattern)
_provider_cache: Dict[str, LLMProvider] = {}


def get_provider(provider_name: Optional[str] = None) -> LLMProvider:
    """Get an LLM provider instance.
    
    This factory function returns the appropriate provider based on the
    provider_name parameter or the LLM_PROVIDER environment variable.
    Provider instances are cached (singleton pattern) to avoid recreating
    them on every call.
    
    Args:
        provider_name: Name of the provider to use ('openai', 'custom', etc.).
                      If None, reads from LLM_PROVIDER env variable (default: 'openai').
    
    Returns:
        An instance of the requested LLM provider.
        
    Raises:
        ValueError: If provider_name is not supported.
    
    Examples:
        >>> provider = get_provider()  # Uses LLM_PROVIDER env or defaults to openai
        >>> provider = get_provider('openai')  # Explicitly use OpenAI
        >>> provider = get_provider('custom')  # Use Custom (when implemented)
    """
    # Determine which provider to use
    if provider_name is None:
        provider_name = os.getenv("LLM_PROVIDER", "openai").lower()
    else:
        provider_name = provider_name.lower()
    
    # Return cached instance if available
    if provider_name in _provider_cache:
        logger.debug(f"Returning cached {provider_name} provider")
        return _provider_cache[provider_name]
    
    # Create new provider instance
    logger.info(f"Creating new {provider_name} provider instance")
    
    if provider_name == "openai":
        provider = OpenAIProvider()
    elif provider_name == "custom":
        # Import here to avoid circular dependency and allow optional Custom
        try:
            from app.ai_agent.providers.custom import CustomProvider
            provider = CustomProvider()
        except ImportError as e:
            raise ValueError(
                f"Custom provider not available. Ensure custom/ directory exists and is properly configured. Error: {e}"
            ) from e
    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider_name}'. "
            f"Supported providers: 'openai', 'custom'"
        )
    
    # Cache and return
    _provider_cache[provider_name] = provider
    logger.info(f"Provider '{provider_name}' initialized successfully")
    return provider


def clear_provider_cache():
    """Clear the provider cache.
    
    This is mainly useful for testing to ensure a fresh provider instance
    is created. In normal usage, the cache should persist for the lifetime
    of the application.
    """
    _provider_cache.clear()
    logger.debug("Provider cache cleared")
