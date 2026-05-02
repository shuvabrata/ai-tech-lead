"""Chains module for AI agent - contains various LLM chain implementations.

This module provides a unified interface for different LLM chains:
- Neo4j chain for graph database queries
- Future chains can be added here (SQL, Vector, etc.)

Main entry point: augment_message_stream() dispatches to appropriate chains.
"""

from .chains import augment_message_stream
from .neo4j_chain import (
    augment_message_with_neo4j,
    augment_message_with_neo4j_stream,
    check_neo4j_relevance,
    query_neo4j_with_chain,
    get_neo4j_graph,
)
from .mcp_chain import augment_message_with_mcp_stream

__all__ = [
    # Main dispatcher
    'augment_message_stream',
    # Neo4j specific functions
    'augment_message_with_neo4j',
    'augment_message_with_neo4j_stream',
    # MCP specific functions
    'augment_message_with_mcp_stream',
    'check_neo4j_relevance',
    'query_neo4j_with_chain',
    'get_neo4j_graph',
]
