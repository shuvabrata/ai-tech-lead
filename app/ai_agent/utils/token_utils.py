"""Utilities for token counting and management."""

import tiktoken

from app.common.logger import logger


def estimate_tokens_from_chars(messages):
    """Estimate token count using character-based approximation.
    
    This is a fallback method for when tiktoken is not available or
    doesn't support the model. Uses the rough approximation that
    1 token ≈ 4 characters for English text.
    
    Args:
        messages: List of message dictionaries with 'content' field
        
    Returns:
        Estimated total number of tokens
    """
    total_chars = sum(len(msg.get("content", "")) for msg in messages)
    estimated_tokens = total_chars // 4
    return estimated_tokens


def count_tokens(messages, model=None):
    """Count the total number of tokens in a list of chat messages.
    
    Attempts to use tiktoken for accurate token counting. If tiktoken
    fails (e.g., unsupported model), falls back to character-based estimation.
    
    Args:
        messages: List of message dictionaries with 'content' field
        model: Model name for token counting. Required parameter.
        
    Returns:
        Total number of tokens (accurate or estimated)
    """
    if model is None:
        raise ValueError("model parameter is required for token counting")
    
    try:
        encoding = tiktoken.encoding_for_model(model)
        num_tokens = 0
        for message in messages:
            num_tokens += len(encoding.encode(message.get("content", "")))
        return num_tokens
    except KeyError:
        # Model not found in tiktoken - fall back to estimation
        logger.warning(
            f"Model '{model}' not supported by tiktoken. "
            f"Using character-based token estimation."
        )
        return estimate_tokens_from_chars(messages)
    except Exception as e:
        # Any other tiktoken error - fall back to estimation
        logger.warning(
            f"Error using tiktoken for model '{model}': {e}. "
            f"Using character-based token estimation."
        )
        return estimate_tokens_from_chars(messages)
