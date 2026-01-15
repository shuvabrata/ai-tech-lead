"""Neo4j chain module for querying graph database using LangChain."""

import os
from pathlib import Path

from dotenv import load_dotenv
import openai
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from app.common.logger import logger

# Load environment variables
load_dotenv()

# Neo4j configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_ENABLED = os.getenv("NEO4J_ENABLED", "false").lower() == "true"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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
    if _neo4j_graph is None and NEO4J_ENABLED:
        try:
            _neo4j_graph = Neo4jGraph(
                url=NEO4J_URI,
                username=NEO4J_USERNAME,
                password=NEO4J_PASSWORD
            )
            logger.info("Neo4j connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            _neo4j_graph = None
    return _neo4j_graph


def check_neo4j_relevance(user_message, model=None):
    """Check if user message is relevant to Neo4j graph database query.
    
    Uses LLM to determine if the query relates to enterprise software
    development data (projects, people, code, etc.).
    
    Args:
        user_message: The user's question/message
        model: OpenAI model to use (defaults to OPENAI_MODEL)
        
    Returns:
        Boolean indicating if the message is relevant to Neo4j data
    """
    if model is None:
        model = OPENAI_MODEL
        
    relevance_prompt = f"""Analyze if this question relates to enterprise software development data including:
- People, teams, organizational structure
- Projects, initiatives, epics, issues, sprints (Jira-like)
- Git repositories, commits, branches, pull requests
- Code files and their relationships
- Work assignments and traceability

Question: {user_message}

Respond with only 'YES' if relevant to the above domains, or 'NO' if not."""
    
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": relevance_prompt}],
            max_tokens=10,
            temperature=0
        )
        answer = response.choices[0].message.content.strip().upper()
        return "YES" in answer
    except Exception as e:
        logger.warning(f"Error checking Neo4j relevance: {e}")
        return False


def query_neo4j_with_chain(user_message, model=None):
    """Query Neo4j using LangChain's GraphCypherQAChain.
    
    This function uses LangChain to automatically:
    1. Convert natural language to Cypher query
    2. Execute the query against Neo4j
    3. Format the results in natural language
    
    Args:
        user_message: The user's question in natural language
        model: OpenAI model to use (defaults to OPENAI_MODEL)
        
    Returns:
        String result from the chain, or None if query fails
    """
    if model is None:
        model = OPENAI_MODEL
        
    graph = get_neo4j_graph()
    if not graph:
        return None
    
    try:
        llm = ChatOpenAI(model=model, temperature=0, openai_api_key=OPENAI_API_KEY)
        
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


def augment_message_with_neo4j(user_message, model=None):
    """Augment user message with Neo4j data if relevant.
    
    This is the main entry point for Neo4j integration. It:
    1. Checks if Neo4j is enabled
    2. Determines if the query is relevant to graph data
    3. Queries Neo4j and augments the message with results
    
    Args:
        user_message: The user's original message
        model: OpenAI model to use (defaults to OPENAI_MODEL)
        
    Returns:
        Augmented message with Neo4j data, or original message if not relevant
    """
    if model is None:
        model = OPENAI_MODEL
        
    if not NEO4J_ENABLED:
        return user_message
    
    # Check if query is relevant
    if not check_neo4j_relevance(user_message, model):
        logger.info("User message not relevant to Neo4j data")
        return user_message
    
    logger.info("User message is relevant to Neo4j")
    
    # Query Neo4j using chain mode
    context_data = query_neo4j_with_chain(user_message, model)
    
    if context_data:
        augmented_message = f"""The following answer was retrieved from the database:

{context_data}

This is the answer to the user's question: "{user_message}"

Please respond with this information in a natural, conversational way."""
        logger.debug(f"Augmented message: {augmented_message}")
        return augmented_message
    
    return user_message
