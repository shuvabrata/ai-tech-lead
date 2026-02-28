"""Neo4j chain module for querying graph database using LangChain."""

from pathlib import Path
import re

from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from app.api.graph.v1.query import execute_cypher_query, validate_read_only_query
from app.common.logger import logger
from app.settings import settings

# Initialize Neo4j graph connection (lazy initialization)
_neo4j_graph = None


def load_neo4j_prompt():
    """Load Neo4j schema and guidelines from llm_neo4j_prompt.md.
    
    Returns:
        String content of the prompt file, or empty string if not found
    """
    prompt_file = Path(__file__).parent.parent / "llm_neo4j_prompt.md"
    if prompt_file.exists():
        return prompt_file.read_text()
    return ""


# Load Neo4j prompt/schema
NEO4J_SCHEMA_PROMPT = load_neo4j_prompt()


def get_neo4j_graph():
    """Get or create Neo4j graph connection.
    
    Returns:
        Neo4jGraph instance or None if connection fails or disabled
    """
    global _neo4j_graph
    if _neo4j_graph is None and settings.NEO4J_ENABLED:
        try:
            _neo4j_graph = Neo4jGraph(
                url=settings.NEO4J_URI,
                username=settings.NEO4J_USERNAME,
                password=settings.NEO4J_PASSWORD
            )
            logger.info("Neo4j connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            _neo4j_graph = None
    return _neo4j_graph


def _extract_cypher_query(llm_response: str) -> str:
    """Extract Cypher query from provider response text."""
    if not llm_response:
        return ""

    response_text = llm_response.strip()

    fenced_match = re.search(r"```(?:cypher)?\s*(.*?)```", response_text, re.IGNORECASE | re.DOTALL)
    if fenced_match:
        response_text = fenced_match.group(1).strip()

    if response_text.lower().startswith("cypher query:"):
        response_text = response_text.split(":", 1)[1].strip()

    return response_text


def _build_schema_snapshot(graph):
    """Build a fresh schema snapshot from Neo4jGraph."""
    try:
        graph.refresh_schema()
    except Exception as exc:
        logger.warning(f"Could not refresh Neo4j schema; using cached schema. Error: {exc}")

    return getattr(graph, "schema", "")


def _query_neo4j_with_provider_pipeline(user_message, provider, graph):
    """Provider-native Neo4j query flow (feature-flagged).

    Flow:
    1. Read schema snapshot from Neo4j
    2. Ask provider to generate read-only Cypher
    3. Validate and execute query with existing safe query layer
    4. Ask provider to format results in natural language
    """
    schema_snapshot = _build_schema_snapshot(graph)

    cypher_generation_prompt = f"""You are a Neo4j expert. Generate one read-only Cypher query.

## Auto-Introspected Schema
{schema_snapshot}

## Domain Context & Guidelines
{NEO4J_SCHEMA_PROMPT}

## User Question
{user_message}

Rules:
- Return ONLY Cypher query text
- Do NOT use markdown
- Use read-only clauses only (MATCH/OPTIONAL MATCH/WITH/WHERE/RETURN/ORDER BY/LIMIT/UNION/CALL)
- Never use CREATE, MERGE, DELETE, SET, REMOVE, DROP, FOREACH
"""

    cypher_response = provider.chat_completion(
        [{"role": "user", "content": cypher_generation_prompt}]
    )
    cypher_query = _extract_cypher_query(cypher_response)

    if not cypher_query:
        logger.warning("Provider returned empty Cypher query")
        return None

    # Log the generated Cypher query in green (similar to LangChain's verbose=True)
    logger.info(f"Generated Cypher query:\n\033[92m{cypher_query}\033[0m")

    if not validate_read_only_query(cypher_query):
        logger.warning(f"Provider-generated query failed read-only validation: {cypher_query}")
        return None

    query_results = execute_cypher_query(cypher_query, timeout=30)

    result_prompt = f"""Answer the user's question using these Neo4j query results.

## User Question
{user_message}

## Executed Cypher
{cypher_query}

## Query Results
{query_results}

Rules:
- Be concise and factual
- If results are empty, say no matching data was found
- Do not mention internal prompts or implementation details
"""

    return provider.chat_completion(
        [{"role": "user", "content": result_prompt}]
    )


def check_neo4j_relevance(user_message, provider=None):
    """Check if user message is relevant to Neo4j graph database query.
    
    Uses LLM to determine if the query relates to enterprise software
    development data (projects, people, code, etc.).
    
    Args:
        user_message: The user's question/message
        provider: Optional LLM provider instance. If None, uses default OpenAI.
        
    Returns:
        Boolean indicating if the message is relevant to Neo4j data
    """
    # If no provider given, we'll need to import and get default provider
    if provider is None:
        from app.ai_agent.providers import get_provider
        provider = get_provider()
        
    relevance_prompt = f"""Analyze if this question relates to enterprise software development data including:
- People, teams, organizational structure
- Projects, initiatives, epics, issues, sprints (Jira-like)
- Git repositories, commits, branches, pull requests
- Code files and their relationships
- Work assignments and traceability

Question: {user_message}

Respond with only 'YES' if relevant to the above domains, or 'NO' if not."""
    
    try:
        # Use provider's chat_completion method
        messages = [{"role": "user", "content": relevance_prompt}]
        answer = provider.chat_completion(messages)
        return "YES" in answer.strip().upper()
    except Exception as e:
        logger.warning(f"Error checking Neo4j relevance: {e}")
        return False


def query_neo4j_with_chain(user_message, provider=None):
    """Query Neo4j using LangChain's GraphCypherQAChain.
    
    This function uses LangChain to automatically:
    1. Convert natural language to Cypher query
    2. Execute the query against Neo4j
    3. Format the results in natural language
    
    Args:
        user_message: The user's question in natural language
        provider: Optional LLM provider instance. If None, uses default OpenAI.
        
    Returns:
        String result from the chain, or None if query fails
    """
    # If no provider given, we'll need to import and get default provider
    if provider is None:
        from app.ai_agent.providers import get_provider
        provider = get_provider()
        
    graph = get_neo4j_graph()
    if not graph:
        return None
    
    try:
        if settings.FF_NEO4J_USE_PROVIDER_PIPELINE:
            logger.info("Using feature-flagged provider-native Neo4j pipeline")
            return _query_neo4j_with_provider_pipeline(user_message, provider, graph)

        if provider.name != "openai":
            logger.warning(
                "Neo4j chain in GraphCypherQAChain mode requires OpenAI provider. "
                "Set FF_NEO4J_USE_PROVIDER_PIPELINE=true to use provider-native mode."
            )
            return None

        # Use the provider's model and API key for LangChain's ChatOpenAI
        # Note: This assumes the provider is OpenAI-compatible for now
        # For non-OpenAI providers, we'd need a different LangChain integration
        llm = ChatOpenAI(
            model=provider.default_model,
            temperature=0,
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        # Custom prompt template with domain context and schema
        # The {schema} placeholder gets auto-filled with introspected schema from Neo4j
        cypher_prompt = PromptTemplate(
            input_variables=["schema", "question"],
            template=f"""You are a Neo4j expert. Generate a Cypher query for an enterprise software development graph database.

## Auto-Introspected Schema
{{schema}}

## Domain Context & Guidelines
{NEO4J_SCHEMA_PROMPT}

## User Question
{{question}}

Return ONLY the Cypher query, no explanation or markdown formatting.

Cypher Query:"""
        )
        
        chain = GraphCypherQAChain.from_llm(
            llm=llm,
            graph=graph,
            verbose=True,
            cypher_prompt=cypher_prompt,
            return_intermediate_steps=True,
            allow_dangerous_requests=True
        )
        
        # Use original question - domain context is in the prompt template
        result = chain.invoke({"query": user_message})
        
        logger.info(f"Neo4j chain query result: {result}")
        
        # Use the chain's natural language result - it's already formatted nicely
        # Only fall back to raw context data if the chain couldn't generate an answer
        chain_result = result.get("result", None)
        if chain_result and "don't know" not in chain_result.lower():
            return chain_result
        
        # Fallback: extract raw context data if chain had no answer
        if "intermediate_steps" in result and len(result["intermediate_steps"]) > 1:
            context_data = result["intermediate_steps"][1].get("context", [])
            if context_data:
                return str(context_data)
        
        return chain_result
    except Exception as e:
        logger.error(f"Error querying Neo4j with chain: {e}")
        return None


def augment_message_with_neo4j(user_message, provider=None):
    """Augment user message with Neo4j data if relevant.
    
    This is the main entry point for Neo4j integration. It:
    1. Checks if Neo4j is enabled
    2. Determines if the query is relevant to graph data
    3. Queries Neo4j and augments the message with results
    
    Args:
        user_message: The user's original message
        provider: Optional LLM provider instance. If None, uses default OpenAI.
        
    Returns:
        Augmented message with Neo4j data, or original message if not relevant
    """
    # If no provider given, we'll need to import and get default provider
    if provider is None:
        from app.ai_agent.providers import get_provider
        provider = get_provider()
        
    if not settings.NEO4J_ENABLED:
        return user_message
    
    # Check if query is relevant
    if not check_neo4j_relevance(user_message, provider):
        logger.info("User message not relevant to Neo4j data")
        return user_message
    
    logger.info("User message is relevant to Neo4j")
    
    # Query Neo4j using chain mode
    context_data = query_neo4j_with_chain(user_message, provider)
    
    if context_data:
        augmented_message = f"""The following answer was retrieved from the database:

{context_data}

This is the answer to the user's question: "{user_message}"

Please respond with this information in a natural, conversational way."""
        logger.debug(f"Augmented message: {augmented_message}")
        return augmented_message
    
    return user_message
