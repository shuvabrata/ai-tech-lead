
"""AI Agent module for managing chat sessions and interactions.

This module handles chat session management including:
- Creating new chat sessions
- Processing chat messages with LLM
- Managing conversation history and token limits
- CLI interface for interactive chat

The module integrates with various chains (e.g., Neo4j) to augment
user messages with relevant data from external sources.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from typing import AsyncIterator

from dotenv import load_dotenv

from common.logger import logger, LogContext
from app.ai_agent.providers import get_provider
from app.ai_agent.chains import augment_message_stream

# In-memory session store: {session_id: [messages]}
_chat_sessions = {}

# In-memory streaming metrics counters.
# Keys: starts, completions, errors, disconnects, total_duration_seconds
_streaming_metrics: dict = {
    "starts": 0,
    "completions": 0,
    "errors": 0,
    "disconnects": 0,
    "total_duration_seconds": 0.0,
}


def get_streaming_metrics() -> dict:
    """Return a snapshot of the current streaming metrics.

    Returns:
        Dictionary with counters for starts, completions, errors, disconnects,
        and total duration in seconds.
    """
    return dict(_streaming_metrics)

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


def _normalize_stream_metadata_payload(metadata_payload: dict) -> dict:
    """Return a normalized metadata payload safe for logging/UI display.

    Keeps the wire schema stable while trimming noisy string fields so very long
    values (for example generated Cypher queries) do not bloat logs/UI.
    """
    safe_payload = dict(metadata_payload)
    safe_sources: list[dict] = []

    for source in safe_payload.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        safe_source = dict(source)

        # Keep long queries readable but bounded.
        query = safe_source.get("neo4j_query")
        if isinstance(query, str) and len(query) > 300:
            safe_source["neo4j_query"] = f"{query[:300]}..."

        # Bound oversized tool lists.
        tools = safe_source.get("tools")
        if isinstance(tools, list) and len(tools) > 10:
            safe_source["tools"] = tools[:10] + [f"+{len(tools) - 10} more"]

        safe_sources.append(safe_source)

    safe_payload["sources"] = safe_sources
    return safe_payload


def _build_and_log_stream_metadata(
    session_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    elapsed_seconds: float,
    model: str,
    sources: list,
) -> dict:
    """Build per-response metadata, normalize it, then log and return it."""
    payload = {
        "tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
        },
        "duration_seconds": round(elapsed_seconds, 2),
        "model": model,
        "sources": sources,
    }
    normalized_payload = _normalize_stream_metadata_payload(payload)
    logger.info(
        "Stream metadata: session_id=%s metadata=%s",
        session_id,
        json.dumps(normalized_payload, default=str),
    )
    return normalized_payload


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
    with LogContext(request_id=session_id):
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
                if event_type == "thinking_chunk":
                    print(f"\033[90m[thinking] {event.get('content', '')}\033[0m")
                elif event_type == "message_chunk":
                    assembled_tokens.append(event.get("content", ""))
                elif event_type == "error":
                    raise RuntimeError(event.get("content", "Stream error"))

        asyncio.run(_drain())

        ai_message = "".join(assembled_tokens)
        total_tokens = _provider.count_tokens(_chat_sessions[session_id], model)
        return ai_message, total_tokens

def end_chat(session_id):
    """End a chat session and clear its history.
    
    Args:
        session_id: UUID of the chat session to end
    """
    _chat_sessions.pop(session_id, None)
    logger.info(f"Chat session ended: {session_id}")


async def stream_chat(
    session_id: str,
    user_message: str,
    model: str = LLM_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> AsyncIterator[str]:
    """Async generator that streams a chat response as SSE-compatible JSON strings.

    Yields one JSON-encoded string per event, each prefixed as a ``data:`` payload
    for consumption by a ``StreamingResponse``.  Event types emitted in order:

    - ``thinking_start``        — signals the start of the augmentation phase.
    - ``thinking_chunk``        — internal context-gathering messages from chains.
    - ``thinking_end``          — signals the end of the augmentation phase.
    - ``message_start``         — signals the start of the LLM token stream.
    - ``message_chunk``         — a single LLM token chunk.
    - ``message_end``           — signals the stream is complete.
    - ``error``                 — emitted if any unrecoverable error occurs.

    When the stream ends normally the assembled response is appended to
    ``_chat_sessions`` so that session history and token counting remain intact
    for subsequent turns.  Token pruning (remove oldest 3 messages after the
    system prompt when ``total_tokens > max_tokens``) is applied before sending
    to the LLM, matching the behaviour of ``do_chat``.

    ``asyncio.CancelledError`` (client disconnect) is re-raised after incrementing
    the disconnect metric counter so that FastAPI can perform proper cleanup.

    Args:
        session_id: UUID of the chat session.
        user_message: The user's message text.
        model: LLM model to use (defaults to the module-level ``LLM_MODEL``).
        max_tokens: Maximum tokens before history pruning.

    Yields:
        SSE-formatted strings (``data: {...}\\n\\n``).

    Raises:
        ValueError: If session_id is not found.
        asyncio.CancelledError: Re-raised on client disconnect after metric update.
    """
    if session_id not in _chat_sessions:
        raise ValueError("Session not found.")

    _streaming_metrics["starts"] += 1
    stream_start = time.monotonic()
    assembled_tokens: list[str] = []

    with LogContext(request_id=session_id):
        logger.info(
            "Stream started: session_id=%s message=%.80s",
            session_id,
            user_message,
        )
        try:
            # ── Phase 1: Augmentation (thinking) ──────────────────────────
            yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"

            final_augmented_message = user_message
            chain_sources: list = []
            try:
                async for event in augment_message_stream(user_message, provider=_provider):
                    if event["type"] == "augmented_message":
                        final_augmented_message = event["content"]
                        chain_sources = event.get("sources_used", [])
                    else:
                        logger.debug("Stream thinking event: %s", event.get("type"))
                        yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                logger.warning("Augmentation phase timed out for session %s", session_id)
                yield f"data: {json.dumps({'type': 'thinking_chunk', 'content': 'Context gathering timed out.'})}\n\n"
            except Exception as aug_exc:
                logger.error("Augmentation phase error for session %s: %s", session_id, aug_exc)
                yield f"data: {json.dumps({'type': 'thinking_chunk', 'content': f'Context gathering failed: {aug_exc}'})}\n\n"

            # ── Phase 2: Build message list with token pruning ─────────────
            messages = list(_chat_sessions[session_id])
            messages.append({"role": "user", "content": final_augmented_message})

            total_tokens = _provider.count_tokens(messages, model)
            logger.info(
                "Stream token count before pruning: session_id=%s tokens=%d max=%d",
                session_id,
                total_tokens,
                max_tokens,
            )
            if total_tokens > max_tokens:
                if len(messages) > 4:
                    messages = [messages[0]] + messages[4:]

            # ── Phase 3: LLM streaming ─────────────────────────────────────
            yield f"data: {json.dumps({'type': 'message_start'})}\n\n"

            try:
                async with asyncio.timeout(180):
                    async for token in _provider.stream_chat_completion(messages, model):
                        assembled_tokens.append(token)
                        yield f"data: {json.dumps({'type': 'message_chunk', 'content': token})}\n\n"
            except asyncio.TimeoutError:
                logger.error("LLM streaming timed out for session %s", session_id)
                _streaming_metrics["errors"] += 1
                yield f"data: {json.dumps({'type': 'error', 'content': 'LLM response timed out.'})}\n\n"
                return

            # ── Phase 4: Save to session history ───────────────────────────
            assembled_response = "".join(assembled_tokens)
            _chat_sessions[session_id].append({"role": "user", "content": final_augmented_message})
            _chat_sessions[session_id].append({"role": "assistant", "content": assembled_response})

            # ── Phase 5: Emit per-response metadata (before message_end so JS
            #            can attach it to the session message on resolve) ────
            elapsed = time.monotonic() - stream_start
            final_tokens = _provider.count_tokens(_chat_sessions[session_id], model)
            metadata_payload = _build_and_log_stream_metadata(
                session_id=session_id,
                prompt_tokens=total_tokens,
                completion_tokens=len(assembled_tokens),
                total_tokens=final_tokens,
                elapsed_seconds=elapsed,
                model=model,
                sources=chain_sources,
            )
            yield f"data: {json.dumps({'type': 'metadata', 'content': metadata_payload})}\n\n"

            yield f"data: {json.dumps({'type': 'message_end'})}\n\n"

            _streaming_metrics["completions"] += 1
            _streaming_metrics["total_duration_seconds"] += elapsed
            logger.info(
                "Stream completed: session_id=%s duration=%.2fs tokens_generated=%d",
                session_id,
                elapsed,
                len(assembled_tokens),
            )

        except asyncio.CancelledError:
            elapsed = time.monotonic() - stream_start
            _streaming_metrics["disconnects"] += 1
            logger.warning(
                "Stream disconnected by client: session_id=%s duration=%.2fs",
                session_id,
                elapsed,
            )
            raise

        except Exception as exc:
            elapsed = time.monotonic() - stream_start
            _streaming_metrics["errors"] += 1
            logger.error(
                "Stream error: session_id=%s error=%s duration=%.2fs",
                session_id,
                exc,
                elapsed,
            )
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

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
