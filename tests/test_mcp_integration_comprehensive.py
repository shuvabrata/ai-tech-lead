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

    def test_atlassian_mcp_enabled_is_boolean(self):
        """Atlassian MCP setting should be a boolean type."""
        assert isinstance(settings.ATLASSIAN_MCP_ENABLED, bool)

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

    def test_atlassian_mcp_token_is_string(self):
        """Atlassian MCP token should be a string type."""
        assert isinstance(settings.ATLASSIAN_MCP_TOKEN, str)

    def test_atlassian_mcp_server_url_is_valid_url(self):
        """Atlassian MCP server URL should be the cloud endpoint."""
        assert isinstance(settings.ATLASSIAN_MCP_SERVER_URL, str)
        assert settings.ATLASSIAN_MCP_SERVER_URL.startswith("https://")

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

    def test_atlassian_check_connection_missing_token_returns_unavailable(self):
        """Atlassian check_connection should fail fast when token is missing."""
        from app.ai_agent.mcp_integration.client_manager import AtlassianMCPClientManager

        manager = AtlassianMCPClientManager(
            atlassian_server_url="https://mcp.atlassian.com/v1/mcp",
            atlassian_token="",
            atlassian_enabled=True,
        )

        result = manager.check_connection()
        assert result["status"] == "unavailable"
        assert result["connected"] is False
        assert result["error"] == "atlassian_mcp_token_missing"

    def test_atlassian_check_connection_malformed_token_returns_unavailable(self):
        """Atlassian check_connection should reject clearly malformed token values."""
        from app.ai_agent.mcp_integration.client_manager import AtlassianMCPClientManager

        manager = AtlassianMCPClientManager(
            atlassian_server_url="https://mcp.atlassian.com/v1/mcp",
            atlassian_token="invalid_token_for_verification",
            atlassian_enabled=True,
        )

        result = manager.check_connection()
        assert result["status"] == "unavailable"
        assert result["connected"] is False
        assert result["error"] == "atlassian_mcp_token_invalid_format"

    def test_execute_tool_call_returns_envelope_structure(self):
        """Tool execution should always return a structured result envelope."""
        from app.ai_agent.mcp_integration.tool_executor import execute_tool_call
        
        result = execute_tool_call("test_tool", {})
        
        # Should have standard envelope structure
        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] in ["success", "error", "unavailable", "failure", "disabled"]

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
        from app.ai_agent.mcp_integration import tool_executor

        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)
        # Isolate from the live DB so the env-disabled fallback is authoritative.
        monkeypatch.setattr(tool_executor, "load_atlassian_mcp_config", lambda: None)

        tools = tool_executor.list_available_tools()
        assert tools == []

    def test_list_available_tools_returns_list(self):
        """Tool listing should return a list (empty or populated)."""
        from app.ai_agent.mcp_integration.tool_executor import list_available_tools
        
        tools = list_available_tools()
        assert isinstance(tools, list)

    def test_list_available_tools_github_only_are_namespaced(self, monkeypatch):
        """GitHub tools should be prefixed with github__ when listed."""
        from app.ai_agent.mcp_integration import tool_executor

        class FakeGithubManager:
            def list_tools(self):
                return [
                    {
                        "type": "function",
                        "function": {
                            "name": "list_commits",
                            "description": "List commits",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ]

        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)
        monkeypatch.setattr(tool_executor, "_build_github_manager", lambda: FakeGithubManager())
        # Isolate from the live DB so the env-disabled fallback is authoritative.
        monkeypatch.setattr(tool_executor, "load_atlassian_mcp_config", lambda: None)

        tools = tool_executor.list_available_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "github__list_commits"

    def test_list_available_tools_atlassian_only_are_namespaced(self, monkeypatch):
        """Atlassian tools should be prefixed with atlassian__ when listed."""
        from app.ai_agent.mcp_integration import tool_executor

        class FakeAtlassianManager:
            def list_tools(self):
                return [
                    {
                        "type": "function",
                        "function": {
                            "name": "getTeamworkGraphContext",
                            "description": "Get context",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ]

        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", True)
        monkeypatch.setattr(tool_executor, "_build_atlassian_manager", lambda: FakeAtlassianManager())

        tools = tool_executor.list_available_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "atlassian__getTeamworkGraphContext"

    def test_list_available_tools_combines_both_backends(self, monkeypatch):
        """Enabled backends should both contribute namespaced tools."""
        from app.ai_agent.mcp_integration import tool_executor

        class FakeGithubManager:
            def list_tools(self):
                return [
                    {
                        "type": "function",
                        "function": {
                            "name": "list_commits",
                            "description": "List commits",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ]

        class FakeAtlassianManager:
            def list_tools(self):
                return [
                    {
                        "type": "function",
                        "function": {
                            "name": "getTeamworkGraphObject",
                            "description": "Get object",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ]

        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", True)
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", True)
        monkeypatch.setattr(tool_executor, "_build_github_manager", lambda: FakeGithubManager())
        monkeypatch.setattr(tool_executor, "_build_atlassian_manager", lambda: FakeAtlassianManager())

        names = [tool["function"]["name"] for tool in tool_executor.list_available_tools()]
        assert "github__list_commits" in names
        assert "atlassian__getTeamworkGraphObject" in names

    def test_execute_tool_call_returns_envelope_structure(self):
        """Tool execution should return a properly structured result envelope."""
        from app.ai_agent.mcp_integration.tool_executor import execute_tool_call
        
        result = execute_tool_call("github__list_issues", {"owner": "test", "repo": "repo"})
        
        # Verify envelope structure
        assert isinstance(result, dict)
        assert "status" in result
        assert "tool_name" in result
        assert result["status"] in ["success", "error", "unavailable", "failure", "tool_error", "disabled"]

    def test_execute_tool_call_with_empty_args(self):
        """Tool execution should handle empty arguments gracefully."""
        from app.ai_agent.mcp_integration.tool_executor import execute_tool_call
        
        result = execute_tool_call("github__list_issues", {})
        
        # Should return envelope, success or graceful failure
        assert isinstance(result, dict)
        assert "status" in result

    def test_execute_tool_call_with_various_argument_types(self):
        """Tool execution should handle various argument types."""
        from app.ai_agent.mcp_integration.tool_executor import execute_tool_call
        
        test_cases = [
            ("github__list_issues", {"owner": "test", "repo": "repo"}),
            ("github__list_issues", {"owner": "test", "repo": "repo", "per_page": 10}),
            ("github__list_issues", {"owner": "test", "repo": "repo", "per_page": "invalid"}),
        ]
        
        for tool_name, args in test_cases:
            result = execute_tool_call(tool_name, args)
            # Each call should return an envelope
            assert isinstance(result, dict)
            assert "status" in result

    def test_execute_tool_call_routes_to_github_backend(self, monkeypatch):
        """Prefixed GitHub tool names should route to the GitHub manager."""
        from app.ai_agent.mcp_integration import tool_executor

        class FakeGithubManager:
            def call_tool(self, tool_name, arguments):
                return {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "status": "success",
                    "result": {},
                }

        monkeypatch.setattr(tool_executor, "_build_github_manager", lambda: FakeGithubManager())

        result = tool_executor.execute_tool_call("github__list_commits", {"owner": "a"})
        assert result["tool_name"] == "list_commits"
        assert result["status"] == "success"

    def test_execute_tool_call_routes_to_atlassian_backend(self, monkeypatch):
        """Prefixed Atlassian tool names should route to the Atlassian manager."""
        from app.ai_agent.mcp_integration import tool_executor

        class FakeAtlassianManager:
            def call_tool(self, tool_name, arguments):
                return {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "status": "success",
                    "result": {},
                }

        monkeypatch.setattr(tool_executor, "_build_atlassian_manager", lambda: FakeAtlassianManager())

        result = tool_executor.execute_tool_call("atlassian__getTeamworkGraphContext", {"objectType": "JIRA_ISSUE"})
        assert result["tool_name"] == "getTeamworkGraphContext"
        assert result["status"] == "success"

    def test_execute_tool_call_with_unknown_prefix_returns_error(self):
        """Unknown or unprefixed tool names should return a structured routing error."""
        from app.ai_agent.mcp_integration.tool_executor import execute_tool_call

        result = execute_tool_call("list_issues", {"owner": "test"})
        assert result["status"] == "error"
        assert result["error"] == "unknown_tool_namespace"


# ============================================================================
# Phase 4: DB-Backed Atlassian MCP Config Resolution
# ============================================================================


class TestDBBackedAtlassianConfig:
    """Validate DB-backed Atlassian MCP config resolution in tool_executor."""

    def test_build_atlassian_manager_uses_db_config_when_available(self, monkeypatch):
        """When the DB loader returns config, the manager should use DB values."""
        from app.ai_agent.mcp_integration import tool_executor

        db_config = {
            "enabled": True,
            "server_url": "https://db-mcp.atlassian.com/v1/mcp",
            "token": "FAKE_ATLASSIAN_TOKEN_DB",
        }
        monkeypatch.setattr(tool_executor, "load_atlassian_mcp_config", lambda: db_config)

        manager = tool_executor._build_atlassian_manager()

        assert manager.atlassian_server_url == "https://db-mcp.atlassian.com/v1/mcp"
        assert manager.atlassian_token == "FAKE_ATLASSIAN_TOKEN_DB"
        assert manager.atlassian_enabled is True

    def test_build_atlassian_manager_falls_back_to_env_when_db_absent(self, monkeypatch):
        """When the DB loader returns None, the manager should use env settings."""
        from app.ai_agent.mcp_integration import tool_executor

        monkeypatch.setattr(tool_executor, "load_atlassian_mcp_config", lambda: None)
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_SERVER_URL", "https://env-mcp.atlassian.com/v1/mcp")
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_TOKEN", "FAKE_ATLASSIAN_TOKEN_ENV")
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", True)

        manager = tool_executor._build_atlassian_manager()

        assert manager.atlassian_server_url == "https://env-mcp.atlassian.com/v1/mcp"
        assert manager.atlassian_token == "FAKE_ATLASSIAN_TOKEN_ENV"
        assert manager.atlassian_enabled is True

    def test_build_atlassian_manager_db_disabled_overrides_env_enabled(self, monkeypatch):
        """DB config with enabled=False must take precedence over env ATLASSIAN_MCP_ENABLED=True."""
        from app.ai_agent.mcp_integration import tool_executor

        db_config = {
            "enabled": False,
            "server_url": "https://db-mcp.atlassian.com/v1/mcp",
            "token": "FAKE_ATLASSIAN_TOKEN_DB",
        }
        monkeypatch.setattr(tool_executor, "load_atlassian_mcp_config", lambda: db_config)
        # Even if env says enabled, DB takes precedence.
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", True)

        manager = tool_executor._build_atlassian_manager()

        assert manager.atlassian_enabled is False

    def test_list_available_tools_uses_db_atlassian_config(self, monkeypatch):
        """list_available_tools should expose Atlassian tools when DB config is enabled."""
        from app.ai_agent.mcp_integration import tool_executor

        class FakeAtlassianManager:
            def list_tools(self):
                return [
                    {
                        "type": "function",
                        "function": {
                            "name": "getTeamworkGraphContext",
                            "description": "Get context",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ]

        db_config = {
            "enabled": True,
            "server_url": "https://db-mcp.atlassian.com/v1/mcp",
            "token": "FAKE_ATLASSIAN_TOKEN_DB",
        }
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        # env says disabled — DB should override.
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)
        monkeypatch.setattr(tool_executor, "load_atlassian_mcp_config", lambda: db_config)
        monkeypatch.setattr(tool_executor, "_build_atlassian_manager", lambda: FakeAtlassianManager())

        tools = tool_executor.list_available_tools()

        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "atlassian__getTeamworkGraphContext"

    def test_list_available_tools_no_atlassian_when_db_disabled(self, monkeypatch):
        """list_available_tools should return no Atlassian tools when DB config is disabled."""
        from app.ai_agent.mcp_integration import tool_executor

        db_config = {
            "enabled": False,
            "server_url": "https://db-mcp.atlassian.com/v1/mcp",
            "token": "",
        }
        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)
        monkeypatch.setattr(tool_executor, "load_atlassian_mcp_config", lambda: db_config)

        tools = tool_executor.list_available_tools()

        atlassian_tools = [t for t in tools if t["function"]["name"].startswith("atlassian__")]
        assert atlassian_tools == []

    def test_loader_exception_triggers_env_fallback(self, monkeypatch):
        """When the loader raises, _build_atlassian_manager should use env settings."""
        from app.ai_agent.mcp_integration import tool_executor

        def _raising_loader():
            raise RuntimeError("DB connection refused")

        monkeypatch.setattr(tool_executor, "load_atlassian_mcp_config", _raising_loader)
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_SERVER_URL", "https://env-fallback.atlassian.com/v1/mcp")
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_TOKEN", "")
        monkeypatch.setattr(settings, "ATLASSIAN_MCP_ENABLED", False)

        # Should not raise; falls back to env settings.
        manager = tool_executor._build_atlassian_manager()
        assert manager.atlassian_enabled is False
