"""Unit tests for provider-native Neo4j chain pipeline."""

from unittest.mock import MagicMock

from app.ai_agent.chains import neo4j_chain
from app.settings import settings


class _FakeGraph:
    """Minimal Neo4j graph test double."""

    def __init__(self):
        self.schema = "(:Project)-[:HAS_ISSUE]->(:Issue)"

    def refresh_schema(self):
        return None


def test_extract_cypher_query_from_fenced_block():
    """Cypher extraction should remove markdown fences and prefix text."""
    response = """```cypher
    MATCH (n) RETURN n LIMIT 5
    ```"""

    extracted = neo4j_chain._extract_cypher_query(response)

    assert extracted == "MATCH (n) RETURN n LIMIT 5"


def test_query_neo4j_with_chain_uses_provider_pipeline_when_flag_enabled(monkeypatch):
    """Feature flag should route execution through provider-native pipeline."""
    monkeypatch.setattr(settings, "FF_NEO4J_USE_PROVIDER_PIPELINE", True)
    monkeypatch.setattr(neo4j_chain, "get_neo4j_graph", lambda: _FakeGraph())
    monkeypatch.setattr(neo4j_chain, "validate_read_only_query", lambda _: True)
    monkeypatch.setattr(neo4j_chain, "execute_cypher_query", lambda *_args, **_kwargs: [{"count": 3}])

    provider = MagicMock()
    provider.name = "custom"
    provider.chat_completion.side_effect = [
        "MATCH (p:Project) RETURN count(p) AS count",
        "There are 3 projects in the graph.",
    ]

    result = neo4j_chain.query_neo4j_with_chain("How many projects are there?", provider=provider)

    assert result == "There are 3 projects in the graph."
    assert provider.chat_completion.call_count == 2


def test_query_neo4j_with_chain_returns_none_for_non_openai_when_flag_disabled(monkeypatch):
    """Without flag, non-OpenAI providers should not use GraphCypherQAChain mode."""
    monkeypatch.setattr(settings, "FF_NEO4J_USE_PROVIDER_PIPELINE", False)
    monkeypatch.setattr(neo4j_chain, "get_neo4j_graph", lambda: _FakeGraph())

    provider = MagicMock()
    provider.name = "custom"

    result = neo4j_chain.query_neo4j_with_chain("List all projects", provider=provider)

    assert result is None
    provider.chat_completion.assert_not_called()
