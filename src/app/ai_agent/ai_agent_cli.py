import sys
import os
from dotenv import load_dotenv

from app.ai_agent.providers import get_provider
from app.ai_agent.ai_agent import new_chat, end_chat, stream_chat

from common.logger import logger, LogContext

# In-memory session store: {session_id: [messages]}
_chat_sessions = {}

# Initialize LLM provider (OpenAI, Custom, etc.)
load_dotenv()
try:
    _provider = get_provider()
except ValueError as e:
    print(f"Error initializing LLM provider: {e}")
    sys.exit(1)

# Use the provider's resolved default model (e.g. CUSTOM_LLM_MODEL for custom provider,
# LLM_MODEL for OpenAI). Avoids cross-provider env var contamination.
LLM_MODEL = _provider.default_model

# Load max tokens from environment or use default
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "16000"))

def start_chat():
    """Start an interactive CLI chat session.
    
    This function provides a simple command-line interface for chatting
    with the AI. Type 'exit' or 'quit' to end the session.
    """
    logger.info(f"AI Chat Program (Provider: {_provider.name})")
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
            with LogContext(request_id=session_id):
                ai_message, total_tokens = do_chat(session_id, user_input)
            print(f"[Token count: {total_tokens}]")
            print(f"AI: {ai_message}")
        except ValueError as ve:
            print(f"Session error: {ve}")
            break
        except RuntimeError as re:
            print(f"LLM error: {re}")
        except Exception as e:
            print(f"Unexpected error: {e}")

def do_chat(session_id, user_message, model=LLM_MODEL, max_tokens=MAX_TOKENS):
    """Perform chat for a session, maintaining message history.

    Synchronous wrapper around :func:`stream_chat` — runs the same async streaming
    code path used by the UI by draining the generator via ``asyncio.run``.  This
    ensures the CLI exercises identical logic to a UI-triggered message, making it
    a reliable dev-testing tool.

    Thinking-phase chunks are printed to stdout in grey; the assembled AI response
    is returned once the stream is complete.

    Args:
        session_id: UUID of the chat session
        user_message: The user's message text
        model: LLM model to use (default from LLM_MODEL env or provider default)
        max_tokens: Maximum tokens allowed before pruning history

    Returns:
        Tuple of (ai_message, total_tokens) where:
            - ai_message: The AI's response text
            - total_tokens: Current total token count for the session

    Raises:
        ValueError: If session_id is not found
        RuntimeError: If LLM API call fails
    """
    logger.info(f"Received message for session {session_id}: {user_message}")
    print(f"\033[92m{user_message}\033[0m")

    if session_id not in _chat_sessions:
        raise ValueError("Session not found.")

    assembled_tokens: list[str] = []

    async def _drain() -> None:
        async for raw in stream_chat(session_id, user_message, model, max_tokens):
            # Each yielded value has the form "data: {...}\n\n"
            payload = raw.removeprefix("data: ").strip()
            if not payload:
                continue
            event = json.loads(payload)
            event_type = event.get("type", "")
            content = event.get("content", "")
            if event_type.startswith("thinking_"):
                print(f"\033[90m[{event_type}] {content}\033[0m")
            elif event_type == "message_chunk":
                assembled_tokens.append(content)
            elif event_type == "message_end":
                full_message = "".join(assembled_tokens)
                print(f"\033[92m[{event_type}] {full_message}\033[0m")
            elif event_type.startswith("message_") or event_type == "metadata":
                print(f"\033[92m[{event_type}] {content}\033[0m")
            elif event_type == "error":
                print(f"\033[91m[{event_type}] {content}\033[0m")
                raise RuntimeError(content or "Stream error")
            else:
                print(f"[{event_type}] {content}")

    asyncio.run(_drain())

    ai_message = "".join(assembled_tokens)
    total_tokens = _provider.count_tokens(_chat_sessions[session_id], model)
    return ai_message, total_tokens

if __name__ == "__main__":
    start_chat()
