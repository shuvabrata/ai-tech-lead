from __future__ import annotations

from typing import AsyncIterator

from app.ai_agent.chains.neo4j_chain import augment_message_with_neo4j, augment_message_with_neo4j_stream
from app.ai_agent.chains.mcp_chain import augment_message_with_mcp_stream
from app.settings import settings


def _compose_multi_source_message(user_message, envelopes):
    """Compose one bounded prompt block from multiple augmentation sources."""
    sections = []

    for envelope in envelopes:
        source = envelope.get("source", "unknown").upper()
        context = envelope.get("context", "")
        if not context:
            continue
        sections.append(f"## {source} Context\n{context}")

    if not sections:
        return user_message

    combined_context = "\n\n".join(sections)
    return (
        "Use the context below to answer the user question.\n\n"
        f"## User Question\n{user_message}\n\n"
        f"{combined_context}\n\n"
        "Rules:\n"
        "- Use only relevant context\n"
        "- If context is insufficient, say so clearly\n"
        "- Do not mention internal implementation details"
    )


async def augment_message_stream(
    user_message: str,
    provider=None,
) -> AsyncIterator[dict]:
    """Async generator that augments a user message and yields thinking chunks.

    This is the streaming counterpart of ``augment_message``.  It follows the
    chain streaming generator contract:

    - Yields ``thinking_chunk`` events from sub-chain generators as they are
      produced.
    - Yields a single ``augmented_message`` event at the end containing the
      final context-enriched string (uses the same multi-source composition
      logic as the synchronous ``augment_message``).

    Note: this function does **not** emit ``thinking_start`` or ``message_start``
    — those are the responsibility of the ``stream_chat`` caller in ``ai_agent.py``.

    Args:
        user_message: The user's original message.
        provider: Optional LLM provider instance.

    Yields:
        dict: SSE-compatible event dictionaries.
    """
    envelopes = []
    neo4j_augmented_message = user_message
    sources_used: list[dict] = []

    if settings.NEO4J_ENABLED:
        async for event in augment_message_with_neo4j_stream(user_message, provider=provider):
            if event["type"] == "augmented_message":
                neo4j_augmented_message = event["content"]
                if neo4j_augmented_message != user_message:
                    envelopes.append({
                        "source": "neo4j",
                        "context": neo4j_augmented_message,
                        "applied": True,
                    })
                    neo4j_source: dict = {"type": "neo4j", "applied": True}
                    neo4j_source.update(event.get("meta") or {})
                    sources_used.append(neo4j_source)
                else:
                    sources_used.append({"type": "neo4j", "applied": False})
            else:
                yield event

    async for event in augment_message_with_mcp_stream(user_message, provider=provider):
        if event["type"] == "augmented_message":
            mcp_envelope = event["content"]
            if isinstance(mcp_envelope, dict) and mcp_envelope.get("applied"):
                envelopes.append(mcp_envelope)
                sources_used.append({
                    "type": "mcp",
                    "applied": True,
                    "tools": [
                        tc.get("name") for tc in mcp_envelope.get("tool_calls", []) if tc.get("name")
                    ],
                })
            else:
                sources_used.append({"type": "mcp", "applied": False})
        else:
            yield event

    if not envelopes:
        yield {"type": "augmented_message", "content": user_message, "sources_used": sources_used}
        return

    if len(envelopes) == 1 and envelopes[0].get("source") == "neo4j":
        yield {"type": "augmented_message", "content": neo4j_augmented_message, "sources_used": sources_used}
        return

    yield {"type": "augmented_message", "content": _compose_multi_source_message(user_message, envelopes), "sources_used": sources_used}