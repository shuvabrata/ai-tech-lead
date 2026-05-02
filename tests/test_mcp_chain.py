"""Unit tests for MCP chain augmentation behavior."""

import pytest

from app.ai_agent.chains import mcp_chain
from app.settings import settings


pytestmark = pytest.mark.unit


class _RelevanceProvider:
    """Provider double that captures relevance prompts and returns fixed answers."""

    def __init__(self, answer: str = "YES"):
        self.answer = answer
        self.last_prompt = ""

    def chat_completion(self, messages):
        self.last_prompt = messages[-1]["content"]
        return self.answer



def test_check_mcp_relevance_prompt_is_dynamic_for_enabled_backends(monkeypatch):
    """Relevance prompt should include backend-specific criteria based on feature flags."""
    provider = _RelevanceProvider(answer="YES")

    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
    # Patch _build_atlassian_manager to simulate DB-driven enablement
    class FakeAtlassianManager:
        atlassian_enabled = True
    monkeypatch.setattr(mcp_chain, "_build_atlassian_manager", lambda: FakeAtlassianManager())

    assert mcp_chain._check_mcp_relevance("Find Jira tickets for sprint 12", provider) is True
    assert "Enabled MCP backends: GitHub, Atlassian" in provider.last_prompt
    assert "GitHub code, pull requests" in provider.last_prompt
    assert "Jira issues/tickets/sprints/epics/boards" in provider.last_prompt
    assert "Confluence pages/spaces/docs" in provider.last_prompt


def test_check_mcp_relevance_prompt_github_only(monkeypatch):
    """GitHub-only mode should not include Atlassian-specific criteria in prompt."""
    provider = _RelevanceProvider(answer="YES")

    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
    class FakeAtlassianManagerDisabled:
        atlassian_enabled = False
    monkeypatch.setattr(mcp_chain, "_build_atlassian_manager", lambda: FakeAtlassianManagerDisabled())

    assert mcp_chain._check_mcp_relevance("Summarize latest commits", provider) is True
    assert "Enabled MCP backends: GitHub" in provider.last_prompt
    assert "Confluence" not in provider.last_prompt


def test_enabled_backends_atlassian_db_disabled_overrides_env(monkeypatch):
    """DB-driven atlassian_enabled=False should exclude Atlassian even when env flag is True."""
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", True)

    class FakeAtlassianManagerDisabled:
        atlassian_enabled = False

    monkeypatch.setattr(mcp_chain, "_build_atlassian_manager", lambda: FakeAtlassianManagerDisabled())

    assert mcp_chain._enabled_backends() == []


def test_enabled_backends_atlassian_manager_exception_treated_as_disabled(monkeypatch):
    """If _build_atlassian_manager raises, Atlassian should be silently excluded."""
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)

    def _raise():
        raise RuntimeError("DB unavailable")

    monkeypatch.setattr(mcp_chain, "_build_atlassian_manager", _raise)

    assert mcp_chain._enabled_backends() == []
