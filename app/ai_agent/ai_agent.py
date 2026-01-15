
"""AI Agent module for managing chat sessions and interactions.

This module handles chat session management including:
- Creating new chat sessions
- Processing chat messages with LLM
- Managing conversation history and token limits
- CLI interface for interactive chat

The module integrates with various chains (e.g., Neo4j) to augment
user messages with relevant data from external sources.
"""

import os
import sys
import uuid

from dotenv import load_dotenv
import openai

from app.common.logger import logger, LogContext
from app.ai_agent.utils.token_utils import count_tokens
from app.ai_agent.chains import augment_message

# In-memory session store: {session_id: [messages]}
_chat_sessions = {}

# Load OpenAI API key and model globally
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("OPENAI_API_KEY not found in environment.")
    sys.exit(1)
openai.api_key = api_key

# Load model name from environment or use default
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

# Load max tokens from environment or use default
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "16000"))


def new_chat(system_prompt="You are a helpful AI assistant."):
    """Create a new chat session and return its session_id (GUID).
    
    Args:
        system_prompt: Initial system prompt for the conversation
        
    Returns:
        session_id: UUID string identifying the new chat session
    """
    session_id = str(uuid.uuid4())
    _chat_sessions[session_id] = [{"role": "system", "content": system_prompt}]
    logger.info(f"New chat session created: {session_id}")
    return session_id

def do_chat(session_id, user_message, model=OPENAI_MODEL, max_tokens=MAX_TOKENS):
    """Perform chat for a session, maintaining message history.
    
    This function:
    1. Validates the session exists
    2. Augments the message with data from chains (e.g., Neo4j)
    3. Manages token limits by pruning old messages if needed
    4. Sends the message to OpenAI and stores the response
    
    Args:
        session_id: UUID of the chat session
        user_message: The user's message text
        model: OpenAI model to use (default from OPENAI_MODEL env)
        max_tokens: Maximum tokens allowed before pruning history
        
    Returns:
        Tuple of (ai_message, total_tokens) where:
            - ai_message: The AI's response text
            - total_tokens: Current total token count for the session
            
    Raises:
        ValueError: If session_id is not found
        RuntimeError: If OpenAI API call fails
    """
    with LogContext(request_id=session_id):
        logger.info(f"Received message for session {session_id}: {user_message}")
        # Print user_message in green color font
        print(f"\033[92m{user_message}\033[0m")
        
        if session_id not in _chat_sessions:
            raise ValueError("Session not found.")
        
        # Augment message with data from chains (e.g., Neo4j)
        augmented_message = augment_message(user_message)
        
        messages = _chat_sessions[session_id]
        messages.append({"role": "user", "content": augmented_message})
        logger.debug(f"Current user_message: {user_message}. Session messages count: {len(messages)}")
        
        # Check token limits and prune if necessary
        total_tokens = count_tokens(messages, model)
        if total_tokens > max_tokens:
            # Remove oldest 3 messages after system prompt
            if len(messages) > 4:
                messages[:] = [messages[0]] + messages[4:]
        
        try:
            response = openai.chat.completions.create(
                model=model,
                messages=messages
            )
            ai_message = response.choices[0].message.content.strip()
            logger.debug(f"AI response: {ai_message}")
            messages.append({"role": "assistant", "content": ai_message})
            return ai_message, count_tokens(messages, model)
        except Exception as e:
            raise RuntimeError(f"OpenAI error: {e}") from e

def end_chat(session_id):
    """End a chat session and clear its history.
    
    Args:
        session_id: UUID of the chat session to end
    """
    _chat_sessions.pop(session_id, None)
    logger.info(f"Chat session ended: {session_id}")

def start_chat():
    """Start an interactive CLI chat session.
    
    This function provides a simple command-line interface for chatting
    with the AI. Type 'exit' or 'quit' to end the session.
    """
    logger.info("Simple OpenAI CLI Chat Program")
    session_id = new_chat()
    print(f"[Session ID: {session_id}]")
    print("Type 'exit' or 'quit' to end the session.")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in {"exit", "quit"}:
            print("Exiting chat.")
            end_chat(session_id)
            break
        
        try:
            ai_message, total_tokens = do_chat(session_id, user_input)
            print(f"[Token count: {total_tokens}]")
            print(f"AI: {ai_message}")
        except ValueError as ve:
            print(f"Session error: {ve}")
            break
        except RuntimeError as re:
            print(f"OpenAI error: {re}")
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    start_chat()
