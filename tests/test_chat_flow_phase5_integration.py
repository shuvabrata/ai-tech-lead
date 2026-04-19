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

    def count_tokens(self, messages, model=None):
        _ = model
        return sum(len(msg.get("content", "")) for msg in messages)

    def chat_completion(self, messages, model=None):
        _ = model
        content = messages[-1]["content"]

        # Relevance check prompt from MCP chain.
        if content.startswith("Determine whether this question requires GitHub repository context"):
            question = ""
            for line in content.splitlines():
                if line.startswith("Question:"):
                    question = line.split(":", 1)[1].strip().lower()
                    break
            if "pull request" in question or "github" in question or "commit" in question:
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
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "mcp_list_pull_requests",
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
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "mcp_list_pull_requests",
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
            "tool_name": "mcp_list_pull_requests",
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
    assert "mcp_list_pull_requests" in final_user_message


def test_rest_chat_flow_non_github_prompt_keeps_baseline(monkeypatch):
    """Non-GitHub prompt should skip MCP tools and keep plain user message flow."""
    fake_provider = _FakeProvider()

    monkeypatch.setattr(ai_agent, "_provider", fake_provider)
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "mcp_list_pull_requests",
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
