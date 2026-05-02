"""Unit tests for multi-source chain composition behavior."""

import pytest

from app.ai_agent.chains import chains
from app.settings import settings


pytestmark = pytest.mark.unit


async def _collect_augmented_message(user_message: str) -> str:
    """Collect the final augmented message from the chain stream."""
    async for event in chains.augment_message_stream(user_message, provider=None):
        if event["type"] == "augmented_message":
            return event["content"]

    raise AssertionError("augment_message_stream did not yield an augmented_message event")


@pytest.mark.asyncio
async def test_augment_message_preserves_neo4j_only_behavior(monkeypatch):
    """Neo4j-only augmentation should return the Neo4j-formatted message unchanged."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", True)
    
    async def _neo4j_stream(*_args, **_kwargs):
        yield {"type": "augmented_message", "content": "neo4j-only-result"}

    async def _mcp_stream(*_args, **_kwargs):
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_neo4j_stream", _neo4j_stream)
    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stream)

    result = await _collect_augmented_message("original question")

    assert result == "neo4j-only-result"


@pytest.mark.asyncio
async def test_augment_message_combines_neo4j_and_mcp_context(monkeypatch):
    """When both sources apply, dispatcher should build a combined bounded prompt block."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", True)
    
    async def _neo4j_stream(*_args, **_kwargs):
        yield {"type": "augmented_message", "content": "neo4j-context"}

    async def _mcp_stream(*_args, **_kwargs):
        yield {
            "type": "augmented_message",
            "content": {"source": "mcp", "applied": True, "context": "mcp-context"},
        }

    monkeypatch.setattr(chains, "augment_message_with_neo4j_stream", _neo4j_stream)
    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stream)

    result = await _collect_augmented_message("original question")

    assert "User Question" in result
    assert "NEO4J Context" in result
    assert "MCP Context" in result
    assert "neo4j-context" in result
    assert "mcp-context" in result
