from app.ai_agent.chains.neo4j_chain import augment_message_with_neo4j
from app.ai_agent.chains.mcp_chain import augment_message_with_mcp
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


def augment_message(user_message, provider=None):
    """Augment user message with data from chains.
    
    Args:
        user_message: The user's message text
        provider: Optional LLM provider instance. If None, chain will use its own default.
        
    Returns:
        Augmented message with chain data, or original message if not relevant
    """
    envelopes = []

    neo4j_augmented_message = user_message
    if settings.NEO4J_ENABLED:
        neo4j_augmented_message = augment_message_with_neo4j(user_message, provider=provider)
        if neo4j_augmented_message != user_message:
            envelopes.append(
                {
                    "source": "neo4j",
                    "context": neo4j_augmented_message,
                    "applied": True,
                }
            )

    mcp_envelope = augment_message_with_mcp(user_message, provider=provider)
    if mcp_envelope.get("applied"):
        envelopes.append(mcp_envelope)

    if not envelopes:
        return user_message

    if len(envelopes) == 1 and envelopes[0].get("source") == "neo4j":
        # Preserve existing behavior for Neo4j-only augmentation.
        return neo4j_augmented_message

    return _compose_multi_source_message(user_message, envelopes)