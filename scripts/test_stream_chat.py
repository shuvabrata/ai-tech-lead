"""Manual test script for stream_chat.

Calls ai_agent.stream_chat directly (no HTTP layer) and prints each SSE event
to the console in real-time so you can verify generation speed and event format.

Usage:
    source .venv/bin/activate
    python scripts/test_stream_chat.py [--message "your question here"]
"""

import asyncio
import argparse
import json
import sys
import os

# Add src/ to path so app imports resolve without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.ai_agent.ai_agent import new_chat, end_chat, stream_chat, get_streaming_metrics


RESET = "\033[0m"
GREY  = "\033[90m"
GREEN = "\033[92m"
RED   = "\033[91m"
CYAN  = "\033[96m"
BOLD  = "\033[1m"


async def run(message: str) -> None:
    session_id = new_chat()
    print(f"{CYAN}Session: {session_id}{RESET}")
    print(f"{CYAN}Message: {message}{RESET}\n")

    thinking_buf: list[str] = []
    response_buf: list[str] = []
    in_thinking = False
    in_message = False

    try:
        async for raw in stream_chat(session_id, message):
            stripped = raw.strip()
            if not stripped.startswith("data: "):
                continue
            event = json.loads(stripped[len("data: "):])
            etype = event.get("type")
            content = event.get("content", "")

            if etype == "thinking_start":
                in_thinking = True
                print(f"{GREY}[thinking]{RESET}", flush=True)

            elif etype == "thinking_chunk":
                thinking_buf.append(content)
                print(f"{GREY}  {content}{RESET}", flush=True)

            elif etype == "thinking_end":
                in_thinking = False

            elif etype == "message_start":
                in_message = True
                print(f"\n{BOLD}[response]{RESET}", flush=True)

            elif etype == "message_chunk":
                response_buf.append(content)
                print(f"{GREEN}{content}{RESET}", end="", flush=True)

            elif etype == "message_end":
                in_message = False
                print()  # newline after response

            elif etype == "error":
                print(f"\n{RED}[error] {content}{RESET}", flush=True)

    finally:
        end_chat(session_id)

    metrics = get_streaming_metrics()
    print(f"\n{CYAN}--- metrics ---{RESET}")
    for k, v in metrics.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual stream_chat test")
    parser.add_argument(
        "--message", "-m",
        default="What is the current status of the project?",
        help="Message to send to the AI",
    )
    args = parser.parse_args()
    asyncio.run(run(args.message))
