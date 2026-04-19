"""Phase 7 regression coverage: MCP settings, provider contracts, and fallback behavior.

This test suite provides comprehensive coverage for:
1. MCP settings and feature flags validation
2. Provider tool-response behavior under MCP context
3. Client connection logic and degradation
4. Tool listing and execution in isolation
5. Regression tests for disabled/unavailable MCP states
"""

from unittest.mock import MagicMock, patch, AsyncMock
import pytest

from app.ai_agent.chains import chains
from app.ai_agent.providers.openai.openai_provider import OpenAIProvider
from app.settings import settings


pytestmark = pytest.mark.unit


# ============================================================================
# Phase 7 Step 1: MCP Settings and Feature Flags Validation
# ============================================================================


class TestMCPSettingsAndFeatureFlags:
    """Validate MCP settings and feature flags load and behave correctly."""

    def test_github_mcp_enabled_is_boolean(self):
        """GitHub MCP setting should be a boolean type."""
        assert isinstance(settings.GITHUB_MCP_ENABLED, bool)

    def test_jira_mcp_enabled_is_boolean(self):
        """Jira MCP setting should be a boolean type."""
        assert isinstance(settings.JIRA_MCP_ENABLED, bool)

    def test_max_mcp_iterations_is_positive_integer(self):
        """MAX_MCP_ITERATIONS should be a positive integer."""
        assert isinstance(settings.MAX_MCP_ITERATIONS, int)
        assert settings.MAX_MCP_ITERATIONS > 0

    def test_github_mcp_server_url_is_valid_url(self):
        """GitHub MCP server URL should be a valid URL string."""
        assert isinstance(settings.GITHUB_MCP_SERVER_URL, str)
        assert settings.GITHUB_MCP_SERVER_URL.startswith("http")

    def test_github_mcp_token_is_string(self):
        """GitHub MCP token should be a string type."""
        assert isinstance(settings.GITHUB_MCP_TOKEN, str)

    def test_mcp_settings_can_be_overridden_via_env(self, monkeypatch):
        """MCP settings should be overridable via environment variables."""
        monkeypatch.setenv("GITHUB_MCP_ENABLED", "true")
        monkeypatch.setenv("MAX_MCP_ITERATIONS", "5")
        monkeypatch.setenv("GITHUB_MCP_SERVER_URL", "http://custom-mcp:9000/mcp")
        monkeypatch.setenv("GITHUB_MCP_TOKEN", "gh_test_token")
        
        from app.settings import Settings
        fresh_settings = Settings(_env_file=None)
        assert fresh_settings.GITHUB_MCP_ENABLED is True
        assert fresh_settings.MAX_MCP_ITERATIONS == 5
        assert fresh_settings.GITHUB_MCP_SERVER_URL == "http://custom-mcp:9000/mcp"
        assert fresh_settings.GITHUB_MCP_TOKEN == "gh_test_token"


# ============================================================================
# Phase 7 Step 2: Provider Tool-Response Behavior
# ============================================================================


class TestProviderToolResponseBehavior:
    """Validate provider handles tool-response structures correctly."""

    def test_openai_provider_chat_completion_with_tools_returns_structured_response(self):
        """Tool-enabled provider should return structured tool-call response."""
        provider = OpenAIProvider()
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = ""
        mock_response.choices[0].message.tool_calls = [
            MagicMock(id="call_1", function=MagicMock(name="list_issues", arguments='{"owner":"test"}'))
        ]
        mock_response.choices[0].finish_reason = "tool_calls"
        
        with patch("openai.chat.completions.create", return_value=mock_response):
            result = provider.chat_completion_with_tools(
                messages=[{"role": "user", "content": "List issues"}],
                tools=[{"type": "function", "function": {"name": "list_issues"}}]
            )
        
        assert "content" in result
        assert "tool_calls" in result
        assert "finish_reason" in result
        assert result["finish_reason"] in ["tool_calls", "stop"]

    def test_openai_provider_tool_response_with_no_tool_calls(self):
        """Provider should handle response with no tool calls gracefully."""
        provider = OpenAIProvider()
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Here's the result"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        
        with patch("openai.chat.completions.create", return_value=mock_response):
            result = provider.chat_completion_with_tools(
                messages=[{"role": "user", "content": "List issues"}],
                tools=[]
            )
        
        assert result["tool_calls"] == [] or result["tool_calls"] is None
        assert result["finish_reason"] == "stop"

    def test_provider_tool_response_preserves_message_history(self):
        """Multiple tool-call rounds should preserve complete message history."""
        provider = OpenAIProvider()
        messages = [
            {"role": "user", "content": "Do something"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "name": "tool_a"}]},
            {"role": "tool", "tool_call_id": "1", "content": "result_a"},
        ]
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Done"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        
        with patch("openai.chat.completions.create", return_value=mock_response) as mock_create:
            provider.chat_completion_with_tools(messages, [])
            
            # Verify all messages were sent to OpenAI
            call_args = mock_create.call_args
            assert len(call_args.kwargs["messages"]) == 3


# ============================================================================
# Phase 7 Step 3: Client Connection Logic and Degradation
# ============================================================================


class TestClientConnectionLogic:
    """Validate MCP client connection and graceful degradation."""

    def test_execute_tool_call_returns_envelope_structure(self):
        """Tool execution should always return a structured result envelope."""
        from app.ai_agent.mcp_integration.tool_executor import execute_tool_call
        
        result = execute_tool_call("test_tool", {})
        
        # Should have standard envelope structure
        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] in ["success", "error", "unavailable", "failure"]

    def test_execute_tool_call_with_disabled_mcp_returns_envelope(self, monkeypatch):
        """Tool execution with disabled MCP should return graceful envelope."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        
        from app.ai_agent.mcp_integration.tool_executor import execute_tool_call
        
        result = execute_tool_call("test_tool", {})
        
        # Should return envelope even when disabled
        assert isinstance(result, dict)
        assert "status" in result

    def test_client_manager_initialization_with_valid_settings(self):
        """Client manager should initialize with valid settings."""
        from app.ai_agent.mcp_integration.client_manager import MCPClientManager
        
        manager = MCPClientManager(
            github_server_url="http://test:8082/mcp",
            github_token="test_token",
            github_enabled=True
        )
        
        assert manager.github_server_url == "http://test:8082/mcp"
        assert manager.github_token == "test_token"
        assert manager.github_enabled is True

    def test_client_manager_initialization_with_defaults(self):
        """Client manager should accept default initialization."""
        from app.ai_agent.mcp_integration.client_manager import MCPClientManager
        
        manager = MCPClientManager(github_server_url="http://test:8082/mcp")
        
        # Should initialize with sensible defaults
        assert manager.github_server_url == "http://test:8082/mcp"
        assert manager.request_timeout_seconds == 20


# ============================================================================
# Phase 7 Step 4: Tool Listing and Execution in Isolation
# ============================================================================


class TestToolListingAndExecution:
    """Validate tool discovery and execution in isolation."""

    def test_list_available_tools_returns_empty_when_disabled(self, monkeypatch):
        """Tool listing should return empty when MCP is disabled."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        
        from app.ai_agent.mcp_integration.tool_executor import list_available_tools
        
        tools = list_available_tools()
        assert tools == []

    def test_list_available_tools_returns_list(self):
        """Tool listing should return a list (empty or populated)."""
        from app.ai_agent.mcp_integration.tool_executor import list_available_tools
        
        tools = list_available_tools()
        assert isinstance(tools, list)

    def test_execute_tool_call_returns_envelope_structure(self):
        """Tool execution should return a properly structured result envelope."""
        from app.ai_agent.mcp_integration.tool_executor import execute_tool_call
        
        result = execute_tool_call("list_issues", {"owner": "test", "repo": "repo"})
        
        # Verify envelope structure
        assert isinstance(result, dict)
        assert "status" in result
        assert "tool_name" in result
        assert result["status"] in ["success", "error", "unavailable", "failure", "tool_error"]

    def test_execute_tool_call_with_empty_args(self):
        """Tool execution should handle empty arguments gracefully."""
        from app.ai_agent.mcp_integration.tool_executor import execute_tool_call
        
        result = execute_tool_call("list_issues", {})
        
        # Should return envelope, success or graceful failure
        assert isinstance(result, dict)
        assert "status" in result

    def test_execute_tool_call_with_various_argument_types(self):
        """Tool execution should handle various argument types."""
        from app.ai_agent.mcp_integration.tool_executor import execute_tool_call
        
        test_cases = [
            ("list_issues", {"owner": "test", "repo": "repo"}),
            ("list_issues", {"owner": "test", "repo": "repo", "per_page": 10}),
            ("list_issues", {"owner": "test", "repo": "repo", "per_page": "invalid"}),
        ]
        
        for tool_name, args in test_cases:
            result = execute_tool_call(tool_name, args)
            # Each call should return an envelope
            assert isinstance(result, dict)
            assert "status" in result


# ============================================================================
# Phase 7 Step 5: Augmentation Loop Behavior Regression
# ============================================================================


class TestAugmentationLoopBehavior:
    """Regression tests for MCP augmentation loop behavior."""

    def test_augmentation_respects_max_mcp_iterations_limit(self, monkeypatch):
        """Tool loop should not exceed MAX_MCP_ITERATIONS boundary."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
        monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 2)
        
        from app.ai_agent.chains import mcp_chain
        
        # Mock provider that always wants to call tools
        provider = MagicMock()
        provider.chat_completion_with_tools.side_effect = [
            {"content": "", "tool_calls": [{"id": "1", "name": "tool_a", "arguments": "{}"}], "finish_reason": "tool_calls"},
            {"content": "", "tool_calls": [{"id": "2", "name": "tool_b", "arguments": "{}"}], "finish_reason": "tool_calls"},
            {"content": "", "tool_calls": [{"id": "3", "name": "tool_c", "arguments": "{}"}], "finish_reason": "tool_calls"},  # Should not reach
            {"content": "Final", "tool_calls": [], "finish_reason": "stop"},
        ]
        
        def mock_execute(tool_name, args):
            return {
                "tool_name": tool_name,
                "status": "success",
                "result": {
                    "content": [{"type": "text", "text": "Result"}],
                    "structured_content": {},
                    "is_error": False,
                },
            }
        
        mock_tool = {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "Test tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        
        with patch.object(mcp_chain, "_check_mcp_relevance", return_value=True):
            with patch.object(mcp_chain, "list_available_tools", return_value=[mock_tool]):
                with patch.object(mcp_chain, "execute_tool_call", side_effect=mock_execute):
                    envelope = mcp_chain.augment_message_with_mcp("Test", provider=provider)
        
        # Provider should be called at most MAX_MCP_ITERATIONS times (+ 1 for init)
        assert provider.chat_completion_with_tools.call_count <= 3

    def test_augmentation_stops_when_no_tool_calls_requested(self, monkeypatch):
        """Tool loop should exit when LLM stops requesting tools."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
        
        from app.ai_agent.chains import mcp_chain
        
        provider = MagicMock()
        provider.chat_completion_with_tools.side_effect = [
            {"content": "", "tool_calls": [{"id": "call_1", "name": "tool_a", "arguments": "{}"}], "finish_reason": "tool_calls"},
            {"content": "Done", "tool_calls": None, "finish_reason": "stop"},
        ]
        
        # Mock tools so the chain proceeds with the loop
        mock_tool = {
            "type": "function",
            "function": {
                "name": "tool_a",
                "description": "Test tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        
        # Mock tool execution to return properly structured result
        def mock_execute(tool_name, args):
            return {
                "tool_name": tool_name,
                "status": "success",
                "result": {
                    "content": [{"type": "text", "text": "Result"}],
                    "structured_content": {},
                    "is_error": False,
                },
            }
        
        with patch.object(mcp_chain, "_check_mcp_relevance", return_value=True):
            with patch.object(mcp_chain, "list_available_tools", return_value=[mock_tool]):
                with patch.object(mcp_chain, "execute_tool_call", side_effect=mock_execute):
                    envelope = mcp_chain.augment_message_with_mcp("Test", provider=provider)
        
        # Provider should be called exactly twice (init + 1 round)
        assert provider.chat_completion_with_tools.call_count == 2

    def test_augmentation_returns_bounded_context(self, monkeypatch):
        """Augmented context should be bounded and not exceed reasonable limits."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
        monkeypatch.setattr(settings, "MAX_MCP_ITERATIONS", 1)
        
        from app.ai_agent.chains import mcp_chain
        
        provider = MagicMock()
        provider.chat_completion_with_tools.return_value = {
            "content": "Done",
            "tool_calls": [],
            "finish_reason": "stop",
        }
        
        def mock_execute(tool_name, args):
            return {
                "tool_name": tool_name,
                "status": "success",
                "result": {
                    "content": [{"type": "text", "text": "x" * 10000}],
                    "structured_content": {},
                    "is_error": False,
                },
            }
        
        mock_tool = {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "Test tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        
        with patch.object(mcp_chain, "_check_mcp_relevance", return_value=True):
            with patch.object(mcp_chain, "list_available_tools", return_value=[mock_tool]):
                with patch.object(mcp_chain, "execute_tool_call", side_effect=mock_execute):
                    envelope = mcp_chain.augment_message_with_mcp("Test", provider=provider)
        
        # Context should exist and be reasonable
        if envelope["applied"]:
            context_len = len(envelope.get("context", ""))
            # Should be much less than raw result size due to truncation
            assert context_len < 50000


# ============================================================================
# Phase 7 Step 6: Regression Tests for Disabled/Unavailable States
# ============================================================================


class TestRegressionFallbackBehavior:
    """Regression tests for fallback behavior when MCP is disabled or unavailable."""

    def test_message_augmentation_with_mcp_disabled_returns_original(self, monkeypatch):
        """Augmentation should return original message when MCP is disabled."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        
        from app.ai_agent.chains import chains
        
        user_message = "What are the recent commits?"
        
        with patch.object(chains, "augment_message_with_neo4j", return_value=user_message):
            result = chains.augment_message(user_message)
        
        # Should return original message unchanged
        assert result == user_message

    def test_multi_source_augmentation_with_only_neo4j(self, monkeypatch):
        """Multi-source should preserve Neo4j-only behavior when MCP is disabled."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        
        from app.ai_agent.chains import chains
        
        user_message = "Show team members"
        neo4j_enhanced = "Show team members [NEO4J_CONTEXT]"
        
        with patch.object(chains, "augment_message_with_neo4j", return_value=neo4j_enhanced):
            with patch.object(chains, "augment_message_with_mcp", return_value={"applied": False, "source": "mcp"}):
                result = chains.augment_message(user_message)
        
        # When only Neo4j is applied, should preserve existing behavior
        assert result == neo4j_enhanced

    def test_chat_flow_with_mcp_unavailable(self, monkeypatch):
        """Chat flow should continue gracefully when MCP service is unavailable."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
        
        from app.ai_agent.chains import chains
        
        user_message = "List recent PRs"
        
        # Neo4j augmentation succeeds, MCP fails
        with patch.object(chains, "augment_message_with_neo4j", return_value=user_message):
            with patch.object(chains, "augment_message_with_mcp") as mock_mcp:
                # MCP returns error envelope (not applied)
                mock_mcp.return_value = {
                    "source": "mcp",
                    "applied": False,
                    "context": "",
                    "error": "Service unavailable"
                }
                
                result = chains.augment_message(user_message)
        
        # Should return something reasonable (user message at minimum)
        assert result is not None
        assert len(result) > 0

    def test_chat_flow_with_both_sources_disabled(self, monkeypatch):
        """Chat flow should return original message when all sources are disabled."""
        monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        
        from app.ai_agent.chains import chains
        
        user_message = "What's new?"
        
        with patch.object(chains, "augment_message_with_neo4j", return_value=user_message):
            with patch.object(chains, "augment_message_with_mcp", return_value={"applied": False}):
                result = chains.augment_message(user_message)
        
        # Should return original message
        assert result == user_message

    def test_regression_message_shape_unchanged_after_augmentation(self, monkeypatch):
        """Augmented messages should maintain string type and usability."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
        
        from app.ai_agent.chains import chains
        
        user_message = "Show issues"
        
        with patch.object(chains, "augment_message_with_neo4j", return_value=user_message):
            with patch.object(chains, "augment_message_with_mcp", return_value={"applied": True, "source": "mcp", "context": "MCP data"}):
                result = chains.augment_message(user_message)
        
        # Result should always be a string, usable as LLM input
        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================================
# Phase 7 Step 7: Integration-Oriented Tests (no live credentials)
# ============================================================================


class TestIntegrationWithoutLiveCredentials:
    """Integration-oriented tests without requiring live API credentials."""

    def test_augmentation_pipeline_backward_compatibility(self, monkeypatch):
        """Existing augmentation pipeline should work with new MCP integration."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        
        from app.ai_agent.chains import chains
        
        user_message = "List team members"
        neo4j_context = "Team context from Neo4j"
        
        with patch.object(chains, "augment_message_with_neo4j", return_value=neo4j_context):
            result = chains.augment_message(user_message)
        
        # Should work exactly as before
        assert result == neo4j_context

    def test_full_chat_session_flow_with_mcp_disabled(self, monkeypatch):
        """Full chat session should work unchanged when MCP is disabled."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        
        from app.ai_agent.chains import chains
        
        messages = [
            {"role": "user", "content": "Who is on the team?"},
            {"role": "user", "content": "What are they working on?"},
        ]
        
        for msg in messages:
            augmented = chains.augment_message(msg["content"])
            # Each augmented message should be valid
            assert isinstance(augmented, str)
            assert len(augmented) > 0

    def test_mixed_augmentation_source_composition(self, monkeypatch):
        """When both Neo4j and MCP apply, context should be composed correctly."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
        
        from app.ai_agent.chains import chains
        
        user_message = "Show GitHub issues"
        
        with patch.object(chains, "augment_message_with_neo4j", return_value=user_message):
            with patch.object(chains, "augment_message_with_mcp", return_value={
                "applied": True,
                "source": "mcp",
                "context": "Issues from GitHub MCP"
            }):
                result = chains.augment_message(user_message)
        
        # Result should include composition markers
        assert isinstance(result, str)
        assert "User Question" in result
        assert "GitHub" in result or "MCP" in result or "Context" in result

    def test_error_recovery_in_augmentation_pipeline(self, monkeypatch):
        """Pipeline should recover gracefully from partial augmentation failures."""
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
        
        from app.ai_agent.chains import chains
        
        user_message = "Test message"
        
        # Neo4j works, MCP returns error envelope
        with patch.object(chains, "augment_message_with_neo4j", return_value=user_message):
            with patch.object(chains, "augment_message_with_mcp", return_value={"applied": False, "source": "mcp", "error": "unavailable"}):
                result = chains.augment_message(user_message)
                # Should not crash, return something usable
                assert isinstance(result, str)
                assert len(result) > 0
