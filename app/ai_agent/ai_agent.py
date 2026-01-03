
import os
import uuid

from dotenv import load_dotenv
import openai
import tiktoken

from app.common.logger import logger

# In-memory session store: {session_id: [messages]}
_chat_sessions = {}

# Load OpenAI API key and model globally
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("OPENAI_API_KEY not found in environment.")
    exit(1)
openai.api_key = api_key

# Load model name from environment or use default
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

# Load max tokens from environment or use default
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "16000"))

def count_tokens(messages, model=None):
    if model is None:
        model = OPENAI_MODEL
    encoding = tiktoken.encoding_for_model(model)
    num_tokens = 0
    for message in messages:
        num_tokens += len(encoding.encode(message.get("content", "")))
    return num_tokens


def new_chat(system_prompt="You are a helpful AI assistant."):
    """Create a new chat session and return its session_id (GUID)."""
    session_id = str(uuid.uuid4())
    _chat_sessions[session_id] = [{"role": "system", "content": system_prompt}]
    return session_id

def do_chat(session_id, user_message, model=OPENAI_MODEL, max_tokens=MAX_TOKENS):
    """Perform chat for a session, maintaining message history."""
    if session_id not in _chat_sessions:
        raise ValueError("Session not found.")
    messages = _chat_sessions[session_id]
    messages.append({"role": "user", "content": user_message})
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
        messages.append({"role": "assistant", "content": ai_message})
        return ai_message, count_tokens(messages, model)
    except Exception as e:
        raise RuntimeError(f"OpenAI error: {e}") from e

def end_chat(session_id):
    """End a chat session and clear its history."""
    _chat_sessions.pop(session_id, None)

def start_chat():
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
