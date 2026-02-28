"""Abstract base class for LLM providers.

This module defines the interface that all LLM providers must implement
to integrate with the AI agent system.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class LLMProvider(ABC):
    """Abstract base class for LLM providers.
    
    All LLM providers (OpenAI, FlexPal, etc.) must inherit from this class
    and implement its abstract methods to ensure compatibility with the
    AI agent system.
    
    The provider abstraction handles:
    - Chat completion requests
    - Token counting (native or estimated)
    - Model validation
    - Provider-specific configuration
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name (e.g., 'openai', 'flexpal').
        
        Returns:
            Provider name as lowercase string
        """
    
    @property
    @abstractmethod
    def default_model(self) -> str:
        """Return the default model name for this provider.
        
        Returns:
            Default model identifier (e.g., 'gpt-3.5-turbo', 'gpt4')
        """
    
    @property
    @abstractmethod
    def supports_native_token_counting(self) -> bool:
        """Indicate if provider supports native token counting.
        
        Returns:
            True if provider has accurate token counting, False if estimation is used
        """
    
    @abstractmethod
    def chat_completion(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        """Send a chat completion request and return the AI's response.
        
        This method handles the provider-specific API call to get a chat completion.
        It should handle message format conversion if needed (e.g., OpenAI's message
        array vs FlexPal's single prompt string).
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys.
                     Format: [{"role": "system|user|assistant", "content": "..."}]
            model: Optional model name to use. If None, uses provider's default_model.
        
        Returns:
            The AI's response text as a string.
            
        Raises:
            RuntimeError: If the API call fails or returns an error.
            ValueError: If the model is not supported by this provider.
        """
    
    @abstractmethod
    def count_tokens(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> int:
        """Count tokens in the message list.
        
        For providers with native token counting (like OpenAI with tiktoken),
        this should return accurate token counts. For others, it should return
        a reasonable estimation (e.g., character count ÷ 4).
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys.
            model: Optional model name for model-specific encoding. If None, uses default.
        
        Returns:
            Total token count (actual or estimated) as an integer.
        """
    
    @abstractmethod
    def validate_model(self, model: str) -> bool:
        """Validate if a model name is supported by this provider.
        
        Args:
            model: Model identifier string to validate.
        
        Returns:
            True if the model is supported, False otherwise.
        """
    
    def _estimate_tokens_from_text(self, text: str) -> int:
        """Estimate token count from text using character-based approximation.
        
        This is a helper method for providers without native token counting.
        Uses a rough approximation of 1 token ≈ 4 characters.
        
        Args:
            text: Text content to estimate tokens for.
        
        Returns:
            Estimated token count.
        """
        return len(text) // 4
    
    def _estimate_tokens_from_messages(self, messages: List[Dict[str, str]]) -> int:
        """Estimate total tokens from a message list.
        
        Helper method that estimates tokens across all messages by summing
        character-based estimates for each message's content.
        
        Args:
            messages: List of message dictionaries.
        
        Returns:
            Estimated total token count.
        """
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        return total_chars // 4
