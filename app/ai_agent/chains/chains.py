import os
from app.ai_agent.chains.neo4j_chain import augment_message_with_neo4j

NEO4J_ENABLED = os.getenv("NEO4J_ENABLED", "false").lower() == "true"

def augment_message(user_message): 
    if NEO4J_ENABLED:
        return augment_message_with_neo4j(user_message)
    return user_message