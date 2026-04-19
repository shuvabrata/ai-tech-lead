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
                "tool_calls": [{"id": "call_1", "name": "mcp_list_issues", "arguments": {"owner": "acme", "repo": "demo"}}],
                "finish_reason": "tool_calls",
            }
        return {"content": "No more tools needed.", "tool_calls": [], "finish_reason": "stop"}


def test_augment_message_with_mcp_returns_unapplied_when_disabled(monkeypatch):
    """MCP envelope should remain unapplied when feature flag is disabled."""
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)

    envelope = mcp_chain.augment_message_with_mcp("What changed in latest PR?", provider=_ToolCallingProvider())

    assert envelope["source"] == "mcp"
    assert envelope["applied"] is False


def test_augment_message_with_mcp_executes_tool_and_builds_context(monkeypatch):
    """Relevant prompts should run tool loop and return bounded MCP context."""
    monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
    monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
    monkeypatch.setattr(mcp_chain, "_check_mcp_relevance", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        mcp_chain,
        "list_available_tools",
        lambda: [
            {
                "type": "function",
                "function": {
                    "name": "mcp_list_issues",
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
            "tool_name": "mcp_list_issues",
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
    assert envelope["tool_calls"] == [{"name": "mcp_list_issues", "status": "success"}]
    assert "Tool: mcp_list_issues" in envelope["context"]
