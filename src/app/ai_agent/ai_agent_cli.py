import sys
from dotenv import load_dotenv

from app.ai_agent.providers import get_provider
from app.ai_agent.ai_agent import new_chat, end_chat, do_chat

from common.logger import logger, LogContext

# Initialize LLM provider (OpenAI, Custom, etc.)
load_dotenv()
try:
    _provider = get_provider()
except ValueError as e:
    print(f"Error initializing LLM provider: {e}")
    sys.exit(1)

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

if __name__ == "__main__":
    start_chat()
