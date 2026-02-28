import os

from app.ai_agent.chains.neo4j_chain import augment_message_with_neo4j

NEO4J_ENABLED = os.getenv("NEO4J_ENABLED", "false").lower() == "true"

def augment_message(user_message, provider=None): 
    """Augment user message with data from chains.
    
    Args:
        user_message: The user's message text
        provider: Optional LLM provider instance. If None, chain will use its own default.
        
    Returns:
        Augmented message with chain data, or original message if not relevant
    """
    if NEO4J_ENABLED:
        return augment_message_with_neo4j(user_message, provider=provider)
    return user_message