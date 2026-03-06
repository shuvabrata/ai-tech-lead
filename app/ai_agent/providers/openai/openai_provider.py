"""OpenAI LLM Provider implementation.

This module implements the LLM provider interface for OpenAI's API,
supporting models like GPT-4o and GPT-5.
"""

import os
from typing import List, Dict, Optional

import openai
from dotenv import load_dotenv

from app.ai_agent.providers.base import LLMProvider
from app.ai_agent.utils.token_utils import count_tokens
from app.common.logger import logger


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider implementation.
    
    This provider uses the OpenAI API for chat completions and supports
    native token counting via tiktoken.
    
    Supported models: gpt-3.5-turbo, gpt-4, gpt-4-turbo, gpt-4o, gpt-5 variants
    """
    
    # Supported OpenAI models
    SUPPORTED_MODELS = {
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-3.5-turbo",
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-4-turbo-preview",
        "gpt-3.5-turbo-16k",
    }
    
    def __init__(self):
        """Initialize the OpenAI provider.
        
        Loads API key from environment and configures the OpenAI client.
        
        Raises:
            ValueError: If OPENAI_API_KEY is not found in environment.
        """
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        openai.api_key = api_key
        self._default_model = os.getenv("LLM_MODEL", "gpt-5")
        logger.info(f"OpenAI provider initialized with model: {self._default_model}")
    
    @property
    def name(self) -> str:
        """Return provider name."""
        return "openai"
    
    @property
    def default_model(self) -> str:
        """Return default model name."""
        return self._default_model
    
    @property
    def supports_native_token_counting(self) -> bool:
        """OpenAI supports native token counting via tiktoken."""
        return True
    
    def chat_completion(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        """Send a chat completion request to OpenAI.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Optional model name. If None, uses default_model.
        
        Returns:
            The AI's response text.
            
        Raises:
            ValueError: If model is not supported.
            RuntimeError: If OpenAI API call fails.
        """
        model_to_use = model or self._default_model
        
        if not self.validate_model(model_to_use):
            raise ValueError(f"Model '{model_to_use}' is not supported by OpenAI provider")
        
        try:
            logger.debug(f"Sending {len(messages)} messages to OpenAI model: {model_to_use}")
            response = openai.chat.completions.create(
                model=model_to_use,
                messages=messages
            )
            ai_message = response.choices[0].message.content.strip()
            logger.debug(f"Received response from OpenAI: {len(ai_message)} characters")
            return ai_message
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"OpenAI error: {e}") from e
    
    def count_tokens(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> int:
        """Count tokens using tiktoken.
        
        Args:
            messages: List of message dicts.
            model: Optional model name for model-specific encoding.
        
        Returns:
            Accurate token count via tiktoken.
        """
        model_to_use = model or self._default_model
        return count_tokens(messages, model_to_use)
    
    def validate_model(self, model: str) -> bool:
        """Validate if model is supported by OpenAI provider.
        
        Args:
            model: Model name to validate.
        
        Returns:
            True if model is in SUPPORTED_MODELS set.
        """
        return model in self.SUPPORTED_MODELS
