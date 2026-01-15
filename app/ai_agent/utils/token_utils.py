"""Utilities for token counting and management."""

import os
import tiktoken
from dotenv import load_dotenv

load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")


def count_tokens(messages, model=None):
    """Count the total number of tokens in a list of chat messages.
    
    Args:
        messages: List of message dictionaries with 'content' field
        model: OpenAI model name (defaults to OPENAI_MODEL from env)
        
    Returns:
        Total number of tokens across all messages
    """
    if model is None:
        model = OPENAI_MODEL
    encoding = tiktoken.encoding_for_model(model)
    num_tokens = 0
    for message in messages:
        num_tokens += len(encoding.encode(message.get("content", "")))
    return num_tokens
