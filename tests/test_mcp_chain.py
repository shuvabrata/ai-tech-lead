"""Unit tests for MCP chain augmentation behavior."""

import pytest

from app.ai_agent.chains import mcp_chain
from app.settings import settings


pytestmark = pytest.mark.unit


class _ToolCallingProvider:
    """Minimal provider double for tool-calling flows."""

    def __init__(self):
        self.calls = 0

    def chat_completion_with_tools(self, messages, tools):
        _ = messages
        _ = tools
        self.calls += 1
        if self.calls == 1:
            return {
                "content": "",
                "tool_calls": [{"id": "call_1", "name": "github__list_issues", "arguments": {"owner": "acme", "repo": "demo"}}],
                "finish_reason": "tool_calls",
            }
        return {"content": "No more tools needed.", "tool_calls": [], "finish_reason": "stop"}


class _RelevanceProvider:
    """Provider double that captures relevance prompts and returns fixed answers."""

    def __init__(self, answer: str = "YES"):
        self.answer = answer
        self.last_prompt = ""

    def chat_completion(self, messages):
        self.last_prompt = messages[-1]["content"]
        return self.answer


def test_augment_message_with_mcp_returns_unapplied_when_disabled(monkeypatch):
    """MCP envelope should remain unapplied when feature flag is disabled."""
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)

    envelope = mcp_chain.augment_message_with_mcp("What changed in latest PR?", provider=_ToolCallingProvider())

    assert envelope["source"] == "mcp"
    assert envelope["applied"] is False


def test_augment_message_with_mcp_executes_tool_and_builds_context(monkeypatch):
    """Relevant prompts should run tool loop and return bounded MCP context."""
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(mcp_chain, "_check_mcp_relevance", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "github__list_issues",
                    "description": "List repository issues",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )
    monkeypatch.setattr(
        mcp_chain,
        "execute_tool_call",
        lambda *_args, **_kwargs: {
            "tool_name": "github__list_issues",
            "status": "success",
            "result": {
                "structured_content": {"total": 1},
                "content": [{"type": "text", "text": "Issue #1"}],
                "is_error": False,
            },
        },
    )

    envelope = mcp_chain.augment_message_with_mcp("Show open issues", provider=_ToolCallingProvider())

    assert envelope["applied"] is True
    assert envelope["tool_calls"] == [{"name": "github__list_issues", "status": "success"}]
    assert "Tool: github__list_issues" in envelope["context"]


def test_augment_message_with_mcp_supports_atlassian_only_mode(monkeypatch):
    """Atlassian-only enablement should still allow MCP augmentation."""
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
    # Patch _build_atlassian_manager to simulate DB-driven enablement
    class FakeAtlassianManager:
        atlassian_enabled = True
    monkeypatch.setattr(mcp_chain, "_build_atlassian_manager", lambda: FakeAtlassianManager())
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(mcp_chain, "_check_mcp_relevance", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "atlassian__getTeamworkGraphContext",
                    "description": "Fetch teamwork graph context",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )
    monkeypatch.setattr(
        mcp_chain,
        "execute_tool_call",
        lambda *_args, **_kwargs: {
            "tool_name": "atlassian__getTeamworkGraphContext",
            "status": "success",
            "result": {
                "structured_content": {"count": 1},
                "content": [{"type": "text", "text": "Atlassian context"}],
                "is_error": False,
            },
        },
    )

    envelope = mcp_chain.augment_message_with_mcp("Show open Jira tickets", provider=_ToolCallingProvider())

    assert envelope["enabled"] is True
    assert envelope["applied"] is True
    assert envelope["tool_calls"] == [{"name": "atlassian__getTeamworkGraphContext", "status": "success"}]


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
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)

    assert mcp_chain._check_mcp_relevance("Summarize latest commits", provider) is True
    assert "Enabled MCP backends: GitHub" in provider.last_prompt
    assert "Confluence" not in provider.last_prompt


def test_augment_message_with_mcp_supports_dual_namespace_tool_calls(monkeypatch):
    """When both backends are enabled, the tool loop should support both namespaces."""
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(mcp_chain, "_check_mcp_relevance", lambda *_args, **_kwargs: True)

    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "github__list_commits",
                    "description": "List commits",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "atlassian__getTeamworkGraphContext",
                    "description": "Get teamwork context",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ],
    )

    class _DualProvider:
        def __init__(self):
            self.calls = 0

        def chat_completion_with_tools(self, messages, tools):
            _ = messages
            _ = tools
            self.calls += 1
            if self.calls == 1:
                return {
                    "content": "",
                    "tool_calls": [
                        {"id": "call_1", "name": "github__list_commits", "arguments": {"repo": "demo"}},
                        {
                            "id": "call_2",
                            "name": "atlassian__getTeamworkGraphContext",
                            "arguments": {"objectType": "JIRA_ISSUE"},
                        },
                    ],
                    "finish_reason": "tool_calls",
                }
            return {"content": "Done", "tool_calls": [], "finish_reason": "stop"}

    monkeypatch.setattr(
        mcp_chain,
        "execute_tool_call",
        lambda name, *_args, **_kwargs: {
            "tool_name": name,
            "status": "success",
            "result": {
                "structured_content": {"tool": name},
                "content": [{"type": "text", "text": f"Result for {name}"}],
                "is_error": False,
            },
        },
    )

    envelope = mcp_chain.augment_message_with_mcp(
        "Summarize GitHub and Jira status", provider=_DualProvider()
    )

    assert envelope["applied"] is True
    names = [item["name"] for item in envelope["tool_calls"]]
    assert "github__list_commits" in names
    assert "atlassian__getTeamworkGraphContext" in names
