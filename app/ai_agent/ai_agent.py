
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
import openai
import tiktoken
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from app.common.logger import logger, LogContext

# In-memory session store: {session_id: [messages]}
_chat_sessions = {}

# Load OpenAI API key and model globally
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("OPENAI_API_KEY not found in environment.")
    sys.exit(1)
openai.api_key = api_key

# Load model name from environment or use default
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

# Load max tokens from environment or use default
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "16000"))

# Neo4j configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_ENABLED = os.getenv("NEO4J_ENABLED", "true").lower() == "true"
NEO4J_MODE = os.getenv("NEO4J_MODE", "chain")  # "chain" or "custom"

# Load Neo4j prompt/schema
def load_neo4j_prompt():
    """Load Neo4j schema and guidelines from neo4j_prompt.md"""
    prompt_file = Path(__file__).parent / "llm_neo4j_prompt.md"
    if prompt_file.exists():
        return prompt_file.read_text()
    return ""

NEO4J_SCHEMA_PROMPT = load_neo4j_prompt()

# Initialize Neo4j graph connection (lazy initialization)
_neo4j_graph = None

def get_neo4j_graph():
    """Get or create Neo4j graph connection"""
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

def count_tokens(messages, model=None):
    if model is None:
        model = OPENAI_MODEL
    encoding = tiktoken.encoding_for_model(model)
    num_tokens = 0
    for message in messages:
        num_tokens += len(encoding.encode(message.get("content", "")))
    return num_tokens


def check_neo4j_relevance(user_message, model=OPENAI_MODEL):
    """Check if user message is relevant to Neo4j graph database query"""
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


def query_neo4j_with_chain(user_message, model=OPENAI_MODEL):
    """Query Neo4j using LangChain's GraphCypherQAChain (Option A)"""
    graph = get_neo4j_graph()
    if not graph:
        return None
    
    try:
        llm = ChatOpenAI(model=model, temperature=0, openai_api_key=api_key)
        
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
        
        # Extract actual data from intermediate steps instead of relying on chain's result
        if "intermediate_steps" in result and len(result["intermediate_steps"]) > 1:
            context_data = result["intermediate_steps"][1].get("context", [])
            if context_data:
                return str(context_data)
        
        # Fallback to chain's result if intermediate steps aren't available
        return result.get("result", None)
    except Exception as e:
        logger.error(f"Error querying Neo4j with chain: {e}")
        return None


def query_neo4j_custom(user_message, model=OPENAI_MODEL):
    """Query Neo4j with custom flow (Option B) - more control"""
    graph = get_neo4j_graph()
    if not graph:
        return None
    
    try:
        # Step 1: Generate Cypher query from natural language
        cypher_generation_prompt = f"""{NEO4J_SCHEMA_PROMPT}

## Task
Generate a Cypher query for the following question. Return ONLY the Cypher query, no explanation.

Question: {user_message}

Cypher Query:"""
        
        response = openai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": cypher_generation_prompt}],
            temperature=0
        )
        cypher_query = response.choices[0].message.content.strip()
        
        # Clean up the query (remove markdown code blocks if present)
        if cypher_query.startswith("```"):
            lines = cypher_query.split("\n")
            cypher_query = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        
        logger.info(f"Generated Cypher query: {cypher_query}")
        
        # Step 2: Execute the query
        result = graph.query(cypher_query)
        logger.info(f"Neo4j custom query result: {result}")
        
        # Step 3: Format results
        if not result:
            return "No data found matching your query."
        
        return str(result)
    except Exception as e:
        logger.error(f"Error in custom Neo4j query: {e}")
        return None


def augment_message_with_neo4j(user_message, model=OPENAI_MODEL):
    """Augment user message with Neo4j data if relevant"""
    if not NEO4J_ENABLED:
        return user_message
    
    # Check if query is relevant
    if not check_neo4j_relevance(user_message, model):
        logger.info("User message not relevant to Neo4j data")
        return user_message
    
    logger.info(f"User message is relevant to Neo4j, using mode: {NEO4J_MODE}")
    
    # Query Neo4j based on selected mode
    if NEO4J_MODE == "chain":
        context_data = query_neo4j_with_chain(user_message, model)
    else:
        context_data = query_neo4j_custom(user_message, model)
    
    if context_data:
        augmented_message = f"""[Context from database]:
{context_data}

[User Question]:
{user_message}"""
        logger.debug(f"Augmented message: {augmented_message}")
        return augmented_message
    
    return user_message


def new_chat(system_prompt="You are a helpful AI assistant."):
    """Create a new chat session and return its session_id (GUID)."""
    session_id = str(uuid.uuid4())
    _chat_sessions[session_id] = [{"role": "system", "content": system_prompt}]
    logger.info(f"New chat session created: {session_id}")
    return session_id

def do_chat(session_id, user_message, model=OPENAI_MODEL, max_tokens=MAX_TOKENS):
    """Perform chat for a session, maintaining message history."""
    with LogContext(request_id=session_id):
        logger.info(f"Received message for session {session_id}")
        if session_id not in _chat_sessions:
            raise ValueError("Session not found.")
        
        # Augment message with Neo4j data if relevant
        augmented_message = augment_message_with_neo4j(user_message, model)
        
        messages = _chat_sessions[session_id]
        messages.append({"role": "user", "content": augmented_message})
        logger.debug(f"Current user_message: {user_message}. Session messages count: {len(messages)}")
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
            logger.debug(f"AI response: {ai_message}")
            messages.append({"role": "assistant", "content": ai_message})
            return ai_message, count_tokens(messages, model)
        except Exception as e:
            raise RuntimeError(f"OpenAI error: {e}") from e

def end_chat(session_id):
    """End a chat session and clear its history."""
    _chat_sessions.pop(session_id, None)
    logger.info(f"Chat session ended: {session_id}")

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
