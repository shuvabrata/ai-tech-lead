"""Integration-oriented chat flow tests for Phase 5 MCP augmentation.

These tests exercise the existing REST chat entry points while stubbing provider and
MCP calls so no live external credentials are required.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.ai_agent import ai_agent
from app.ai_agent.chains import mcp_chain
from app.settings import settings


pytestmark = pytest.mark.unit


class _FakeProvider:
    """Provider test double that supports both plain and tool-enabled chat methods."""

    def __init__(self) -> None:
        self.default_model = "gpt-5"
        self.final_messages = []
        self.tool_calls_count = 0
        self._tool_round = 0
        self._detected_domain = ""

    def count_tokens(self, messages, model=None):
        _ = model
        return sum(len(msg.get("content", "")) for msg in messages)

    def chat_completion(self, messages, model=None):
        _ = model
        content = messages[-1]["content"]

        # Relevance check prompt from MCP chain.
        if content.startswith("Determine whether this question requires MCP context"):
            question = ""
            for line in content.splitlines():
                if line.startswith("Question:"):
                    question = line.split(":", 1)[1].strip().lower()
                    break
            self._detected_domain = ""
            if "jira" in question or "ticket" in question or "epic" in question or "sprint" in question:
                self._detected_domain = "atlassian"
                return "YES"
            if "confluence" in question or "space" in question or "documentation" in question:
                self._detected_domain = "atlassian"
                return "YES"
            if "pull request" in question or "github" in question or "commit" in question:
                self._detected_domain = "github"
                return "YES"
            return "NO"

        # Keep an immutable snapshot because the caller mutates the list afterward.
        self.final_messages = [dict(msg) for msg in messages]
        return "assistant-final-response"

    def chat_completion_with_tools(self, messages, tools, model=None):
        _ = messages
        _ = tools
        _ = model
        self.tool_calls_count += 1
        self._tool_round += 1

        if self._tool_round == 1:
            if self._detected_domain == "atlassian":
                return {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "name": "atlassian__getTeamworkGraphContext",
                            "arguments": {"objectType": "JIRA_ISSUE"},
                        }
                    ],
                    "finish_reason": "tool_calls",
                }
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "github__list_pull_requests",
                        "arguments": {"owner": "acme", "repo": "demo"},
                    }
                ],
                "finish_reason": "tool_calls",
            }

        return {"content": "Tooling complete", "tool_calls": [], "finish_reason": "stop"}


@pytest.fixture(autouse=True)
def _reset_chat_sessions():
    """Ensure chat session global state does not leak across tests."""
    ai_agent._chat_sessions.clear()
    yield
    ai_agent._chat_sessions.clear()


def test_rest_chat_flow_github_prompt_injects_mcp_context(monkeypatch):
    """GitHub-related prompt should trigger MCP tool loop and context injection."""
    fake_provider = _FakeProvider()

    monkeypatch.setattr(ai_agent, "_provider", fake_provider)
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "github__list_pull_requests",
                    "description": "List pull requests",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )
    monkeypatch.setattr(
        mcp_chain,
        "execute_tool_call",
        lambda *_args, **_kwargs: {
            "tool_name": "github__list_pull_requests",
            "status": "success",
            "result": {
                "structured_content": {"count": 1},
                "content": [{"type": "text", "text": "PR #42 - Fix latency"}],
                "is_error": False,
            },
        },
    )

    client = TestClient(app)
    create_res = client.post("/api/v1/chats/", json={"system_prompt": "You are helpful."})
    assert create_res.status_code == 201

    session_id = create_res.json()["session_id"]
    message_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={"message": "Summarize recent GitHub pull requests for project demo."},
    )

    assert message_res.status_code == 200
    assert message_res.json()["ai_message"] == "assistant-final-response"
    assert fake_provider.tool_calls_count >= 1

    # Ensure final provider call got a composed MCP context prompt.
    final_user_message = fake_provider.final_messages[-1]["content"]
    assert "MCP Context" in final_user_message
    assert "github__list_pull_requests" in final_user_message


def test_rest_chat_flow_atlassian_jira_prompt_injects_mcp_context(monkeypatch):
    """Jira-related prompt should trigger Atlassian MCP tool loop and context injection."""
    fake_provider = _FakeProvider()

    monkeypatch.setattr(ai_agent, "_provider", fake_provider)
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "atlassian__getTeamworkGraphContext",
                    "description": "Fetch teamwork context",
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
                "structured_content": {"count": 2},
                "content": [{"type": "text", "text": "Jira issues in current sprint"}],
                "is_error": False,
            },
        },
    )

    client = TestClient(app)
    create_res = client.post("/api/v1/chats/", json={"system_prompt": "You are helpful."})
    assert create_res.status_code == 201

    session_id = create_res.json()["session_id"]
    message_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={"message": "Find open Jira tickets for Project Alpha sprint."},
    )

    assert message_res.status_code == 200
    assert message_res.json()["ai_message"] == "assistant-final-response"
    assert fake_provider.tool_calls_count >= 1

    final_user_message = fake_provider.final_messages[-1]["content"]
    assert "MCP Context" in final_user_message
    assert "atlassian__getTeamworkGraphContext" in final_user_message


def test_rest_chat_flow_atlassian_confluence_prompt_injects_mcp_context(monkeypatch):
    """Confluence-related prompt should trigger Atlassian MCP augmentation."""
    fake_provider = _FakeProvider()

    monkeypatch.setattr(ai_agent, "_provider", fake_provider)
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "atlassian__getTeamworkGraphObject",
                    "description": "Fetch teamwork object",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )
    monkeypatch.setattr(
        mcp_chain,
        "execute_tool_call",
        lambda *_args, **_kwargs: {
            "tool_name": "atlassian__getTeamworkGraphObject",
            "status": "success",
            "result": {
                "structured_content": {"type": "confluence_page"},
                "content": [{"type": "text", "text": "Confluence design doc summary"}],
                "is_error": False,
            },
        },
    )

    client = TestClient(app)
    create_res = client.post("/api/v1/chats/", json={})
    assert create_res.status_code == 201

    session_id = create_res.json()["session_id"]
    message_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={"message": "Summarize Confluence documentation for onboarding."},
    )

    assert message_res.status_code == 200
    assert message_res.json()["ai_message"] == "assistant-final-response"
    final_user_message = fake_provider.final_messages[-1]["content"]
    assert "MCP Context" in final_user_message
    assert "atlassian__getTeamworkGraphObject" in final_user_message


def test_rest_chat_flow_both_backends_github_prompt_uses_github_tools_only(monkeypatch):
    """With both backends enabled, GitHub prompt should execute only GitHub tools."""
    fake_provider = _FakeProvider()
    executed_tools = []

    monkeypatch.setattr(ai_agent, "_provider", fake_provider)
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "github__list_pull_requests",
                    "description": "List pull requests",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "atlassian__getTeamworkGraphContext",
                    "description": "Atlassian context",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ],
    )

    def _execute(name, *_args, **_kwargs):
        executed_tools.append(name)
        return {
            "tool_name": name,
            "status": "success",
            "result": {
                "structured_content": {"name": name},
                "content": [{"type": "text", "text": f"Result {name}"}],
                "is_error": False,
            },
        }

    monkeypatch.setattr(mcp_chain, "execute_tool_call", _execute)

    client = TestClient(app)
    session_id = client.post("/api/v1/chats/", json={}).json()["session_id"]
    message_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={"message": "Summarize recent GitHub commits and pull requests."},
    )

    assert message_res.status_code == 200
    assert all(name.startswith("github__") for name in executed_tools)


def test_rest_chat_flow_atlassian_unavailable_does_not_break_response(monkeypatch):
    """Atlassian tool failures should not break the overall chat response."""
    fake_provider = _FakeProvider()

    monkeypatch.setattr(ai_agent, "_provider", fake_provider)
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "atlassian__getTeamworkGraphContext",
                    "description": "Fetch teamwork context",
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
            "status": "unavailable",
            "error": "upstream_timeout",
            "result": None,
        },
    )

    client = TestClient(app)
    session_id = client.post("/api/v1/chats/", json={}).json()["session_id"]
    message_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={"message": "Get Jira blockers for this sprint."},
    )

    assert message_res.status_code == 200
    assert message_res.json()["ai_message"] == "assistant-final-response"


def test_rest_chat_flow_atlassian_disabled_preserves_github_only_path(monkeypatch):
    """Disabling Atlassian should leave GitHub-only MCP behavior intact."""
    fake_provider = _FakeProvider()
    executed_tools = []

    monkeypatch.setattr(ai_agent, "_provider", fake_provider)
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "github__list_pull_requests",
                    "description": "List pull requests",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    def _execute(name, *_args, **_kwargs):
        executed_tools.append(name)
        return {
            "tool_name": name,
            "status": "success",
            "result": {
                "structured_content": {"ok": True},
                "content": [{"type": "text", "text": "OK"}],
                "is_error": False,
            },
        }

    monkeypatch.setattr(mcp_chain, "execute_tool_call", _execute)

    client = TestClient(app)
    create_res = client.post("/api/v1/chats/", json={"system_prompt": "You are helpful."})
    session_id = create_res.json()["session_id"]

    message_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={"message": "Summarize recent GitHub pull requests for project demo."},
    )

    assert message_res.status_code == 200
    assert executed_tools
    assert all(name.startswith("github__") for name in executed_tools)


def test_rest_chat_flow_session_continuity_unchanged(monkeypatch):
    """Session handling and history should remain stable across multiple chat turns."""
    fake_provider = _FakeProvider()

    monkeypatch.setattr(ai_agent, "_provider", fake_provider)
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)

    client = TestClient(app)
    create_res = client.post("/api/v1/chats/", json={"system_prompt": "You are helpful."})
    assert create_res.status_code == 201
    session_id = create_res.json()["session_id"]

    first_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={"message": "First question"},
    )
    second_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={"message": "Second question"},
    )

    assert first_res.status_code == 200
    assert second_res.status_code == 200
    assert session_id in ai_agent._chat_sessions
    assert len(ai_agent._chat_sessions[session_id]) >= 5


def test_rest_chat_flow_non_github_prompt_keeps_baseline(monkeypatch):
    """Non-GitHub prompt should skip MCP tools and keep plain user message flow."""
    fake_provider = _FakeProvider()

    monkeypatch.setattr(ai_agent, "_provider", fake_provider)
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "github__list_pull_requests",
                    "description": "List pull requests",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    client = TestClient(app)
    create_res = client.post("/api/v1/chats/", json={})
    assert create_res.status_code == 201

    session_id = create_res.json()["session_id"]
    plain_message = "What is the agenda for tomorrow's planning meeting?"
    message_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={"message": plain_message},
    )

    assert message_res.status_code == 200
    assert message_res.json()["ai_message"] == "assistant-final-response"
    assert fake_provider.tool_calls_count == 0

    final_user_message = fake_provider.final_messages[-1]["content"]
    assert final_user_message == plain_message
