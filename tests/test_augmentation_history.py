"""Unit tests for conversation history wiring across all augmentation chains.

Verifies that:
- augment_message_stream() accepts and threads conversation_history to all chains
- Neo4j, ES, and MCP chain stubs receive the history argument correctly
- chains.py composition handles the ES envelope correctly (applied/not-applied)
- Existing Neo4j-only and multi-source composition behaviour is preserved
"""

from __future__ import annotations

import pytest

from app.ai_agent.chains import chains
from app.settings import settings

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect(user_message: str, history=None) -> tuple[str | dict, list]:
    """Drain augment_message_stream and return (content, sources_used)."""
    content = user_message
    sources: list = []
    async for event in chains.augment_message_stream(
        user_message, provider=None, conversation_history=history
    ):
        if event["type"] == "augmented_message":
            content = event["content"]
            sources = event.get("sources_used", [])
    return content, sources


# ---------------------------------------------------------------------------
# Signature: conversation_history parameter flows through
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_history_passed_to_neo4j_chain(monkeypatch):
    """Neo4j chain receives conversation_history kwarg."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", True)
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", False)

    received: dict = {}

    async def _neo4j_stub(msg, provider=None, conversation_history=None):
        received["history"] = conversation_history
        yield {"type": "augmented_message", "content": msg}

    async def _mcp_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_neo4j_stream", _neo4j_stub)
    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stub)

    history = [{"role": "user", "content": "prior turn"}]
    await _collect("hello", history=history)

    assert received["history"] == history


@pytest.mark.asyncio
async def test_history_passed_to_mcp_chain(monkeypatch):
    """MCP chain receives conversation_history kwarg."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", False)

    received: dict = {}

    async def _mcp_stub(msg, provider=None, conversation_history=None):
        received["history"] = conversation_history
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stub)

    history = [{"role": "user", "content": "prior turn"}]
    await _collect("hello", history=history)

    assert received["history"] == history


@pytest.mark.asyncio
async def test_history_passed_to_es_chain(monkeypatch):
    """ES chain receives conversation_history kwarg."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", True)

    received: dict = {}

    async def _es_stub(msg, provider=None, conversation_history=None):
        received["history"] = conversation_history
        yield {"type": "augmented_message", "content": {"source": "elasticsearch", "applied": False, "context": ""}}

    async def _mcp_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_es_stream", _es_stub)
    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stub)

    history = [{"role": "user", "content": "prior turn"}]
    await _collect("hello", history=history)

    assert received["history"] == history


@pytest.mark.asyncio
async def test_none_history_passed_when_omitted(monkeypatch):
    """When no history is provided, None is passed to all chains."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", False)

    received: dict = {}

    async def _mcp_stub(msg, provider=None, conversation_history=None):
        received["history"] = conversation_history
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stub)

    await _collect("hello")  # no history argument

    assert received["history"] is None


# ---------------------------------------------------------------------------
# ES envelope composition in chains.py
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_es_applied_envelope_added_to_sources(monkeypatch):
    """When ES chain fires (applied=True), sources_used contains an ES entry."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", True)

    async def _es_stub(msg, provider=None, conversation_history=None):
        yield {
            "type": "augmented_message",
            "content": {
                "source": "elasticsearch",
                "applied": True,
                "context": "some ES context",
                "query": {"q": "bugs"},
                "total_hits": 5,
            },
        }

    async def _mcp_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_es_stream", _es_stub)
    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stub)

    _, sources = await _collect("find bugs")

    es_source = next((s for s in sources if s.get("type") == "elasticsearch"), None)
    assert es_source is not None
    assert es_source["applied"] is True
    assert es_source["total_hits"] == 5


@pytest.mark.asyncio
async def test_es_not_applied_envelope_recorded_in_sources(monkeypatch):
    """When ES chain does not fire, sources_used records it as not applied."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", True)

    async def _es_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": {"source": "elasticsearch", "applied": False, "context": ""}}

    async def _mcp_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_es_stream", _es_stub)
    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stub)

    _, sources = await _collect("hello")

    es_source = next((s for s in sources if s.get("type") == "elasticsearch"), None)
    assert es_source is not None
    assert es_source["applied"] is False


@pytest.mark.asyncio
async def test_es_context_included_in_composed_message(monkeypatch):
    """ES context block appears in the final composed message."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", True)

    async def _es_stub(msg, provider=None, conversation_history=None):
        yield {
            "type": "augmented_message",
            "content": {
                "source": "elasticsearch",
                "applied": True,
                "context": "ES entity context here",
                "query": {},
                "total_hits": 1,
            },
        }

    async def _mcp_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_es_stream", _es_stub)
    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stub)

    content, _ = await _collect("find bugs")

    assert "ELASTICSEARCH Context" in content
    assert "ES entity context here" in content
    assert "User Question" in content


@pytest.mark.asyncio
async def test_es_disabled_block_is_skipped(monkeypatch):
    """When ELASTICSEARCH_ENABLED=false, the ES block is not called."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", False)

    called = {"es": False}

    async def _es_stub(msg, provider=None, conversation_history=None):
        called["es"] = True
        yield {"type": "augmented_message", "content": {"applied": False}}

    async def _mcp_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_es_stream", _es_stub)
    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stub)

    await _collect("find bugs")

    assert called["es"] is False


@pytest.mark.asyncio
async def test_neo4j_only_special_case_preserved_with_es_disabled(monkeypatch):
    """The existing Neo4j-only early-return path is not broken by the ES block."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", True)
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", False)

    async def _neo4j_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": "neo4j-only-result"}

    async def _mcp_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_neo4j_stream", _neo4j_stub)
    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stub)

    content, _ = await _collect("who reviewed Alice's PR?")

    assert content == "neo4j-only-result"


@pytest.mark.asyncio
async def test_neo4j_and_es_both_applied_compose_correctly(monkeypatch):
    """When both Neo4j and ES fire, both contexts appear in the composed message."""
    monkeypatch.setattr(settings, "NEO4J_ENABLED", True)
    monkeypatch.setattr(settings, "ELASTICSEARCH_ENABLED", True)

    async def _neo4j_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": "neo4j graph context"}

    async def _es_stub(msg, provider=None, conversation_history=None):
        yield {
            "type": "augmented_message",
            "content": {
                "source": "elasticsearch",
                "applied": True,
                "context": "es search context",
                "query": {},
                "total_hits": 2,
            },
        }

    async def _mcp_stub(msg, provider=None, conversation_history=None):
        yield {"type": "augmented_message", "content": {"source": "mcp", "applied": False, "context": ""}}

    monkeypatch.setattr(chains, "augment_message_with_neo4j_stream", _neo4j_stub)
    monkeypatch.setattr(chains, "augment_message_with_es_stream", _es_stub)
    monkeypatch.setattr(chains, "augment_message_with_mcp_stream", _mcp_stub)

    content, _ = await _collect("find Alice's issues")

    assert "NEO4J Context" in content
    assert "ELASTICSEARCH Context" in content
    assert "neo4j graph context" in content
    assert "es search context" in content


# ---------------------------------------------------------------------------
# Neo4j _format_history_block
# ---------------------------------------------------------------------------

def test_neo4j_format_history_block_empty():
    from app.ai_agent.chains.neo4j_chain import _format_history_block
    assert _format_history_block(None) == ""
    assert _format_history_block([]) == ""


def test_neo4j_format_history_block_formats_correctly():
    from app.ai_agent.chains.neo4j_chain import _format_history_block
    history = [
        {"role": "user", "content": "Tell me about Alice"},
        {"role": "assistant", "content": "Alice is a developer."},
    ]
    result = _format_history_block(history)
    assert "User: Tell me about Alice" in result
    assert "Assistant: Alice is a developer." in result
    assert "## Conversation History" in result
