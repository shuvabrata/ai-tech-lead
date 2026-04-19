"""Unit tests for multi-source chain composition behavior."""

import pytest

from app.ai_agent.chains import chains
from app.settings import settings


pytestmark = pytest.mark.unit


def test_augment_message_preserves_neo4j_only_behavior(monkeypatch):
    """Neo4j-only augmentation should return the Neo4j-formatted message unchanged."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", True)
    monkeypatch.setattr(chains, "augment_message_with_neo4j", lambda *_args, **_kwargs: "neo4j-only-result")
    monkeypatch.setattr(chains, "augment_message_with_mcp", lambda *_args, **_kwargs: {"source": "mcp", "applied": False, "context": ""})

    result = chains.augment_message("original question", provider=None)

    assert result == "neo4j-only-result"


def test_augment_message_combines_neo4j_and_mcp_context(monkeypatch):
    """When both sources apply, dispatcher should build a combined bounded prompt block."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", True)
    monkeypatch.setattr(chains, "augment_message_with_neo4j", lambda *_args, **_kwargs: "neo4j-context")
    monkeypatch.setattr(
        chains,
        "augment_message_with_mcp",
        lambda *_args, **_kwargs: {"source": "mcp", "applied": True, "context": "mcp-context"},
    )

    result = chains.augment_message("original question", provider=None)

    assert "User Question" in result
    assert "NEO4J Context" in result
    assert "MCP Context" in result
    assert "neo4j-context" in result
    assert "mcp-context" in result
