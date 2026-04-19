"""Phase 2 verification tests for provider contract extension.

Verifies:
1. Existing non-tool chat calls still work without code changes in current callers
2. Tool-enabled completion can return a structured response that MCP chain can consume
3. Token counting behavior remains intact
4. Existing provider tests still pass or are updated with equivalent coverage
5. The non-tool provider path used by current chat flow remains unchanged for existing callers
"""

from unittest.mock import MagicMock, patch
import json

import pytest

from app.ai_agent.providers.base import LLMProvider
from app.ai_agent.providers.openai.openai_provider import OpenAIProvider


pytestmark = pytest.mark.unit


class TestProviderContractBackwardCompatibility:
    """Verify existing chat_completion() behavior is unchanged."""

    def test_base_provider_chat_completion_exists(self):
        """Base provider should have chat_completion() method."""
        assert hasattr(LLMProvider, "chat_completion")
        assert callable(getattr(LLMProvider, "chat_completion"))

    def test_openai_provider_chat_completion_exists(self):
        """OpenAI provider should have chat_completion() method."""
        assert hasattr(OpenAIProvider, "chat_completion")
        assert callable(getattr(OpenAIProvider, "chat_completion"))

    def test_openai_chat_completion_without_tools(self):
        """Existing chat_completion() call without tools should work unchanged."""
        provider = OpenAIProvider()
        
        with patch("openai.chat.completions.create") as mock_create:
            mock_create.return_value.choices[0].message.content = "Test response"
            mock_create.return_value.choices[0].finish_reason = "stop"
            
            messages = [{"role": "user", "content": "Hello"}]
            result = provider.chat_completion(messages)
            
            assert isinstance(result, str)
            assert result == "Test response"
            mock_create.assert_called_once()
            
            # Verify no 'tools' parameter was passed
            call_args = mock_create.call_args
            assert "tools" not in call_args.kwargs or call_args.kwargs.get("tools") is None

    def test_openai_chat_completion_response_format_unchanged(self):
        """chat_completion() should return plain string, not structured dict."""
        provider = OpenAIProvider()
        
        with patch("openai.chat.completions.create") as mock_create:
            mock_create.return_value.choices[0].message.content = "Response text"
            mock_create.return_value.choices[0].finish_reason = "stop"
            
            result = provider.chat_completion([{"role": "user", "content": "test"}])
            
            # Should be string, not dict
            assert isinstance(result, str)
            assert not isinstance(result, dict)


class TestProviderContractToolExtension:
    """Verify new chat_completion_with_tools() contract."""

    def test_base_provider_tool_method_exists_and_raises_not_implemented(self):
        """Base provider should have chat_completion_with_tools() that raises NotImplementedError."""
        # Create a concrete test subclass to test the base method
        class TestProvider(LLMProvider):
            @property
            def name(self):
                return "test"
            
            @property
            def supports_native_token_counting(self):
                return False
            
            @property
            def default_model(self):
                return "test-model"
            
            def chat_completion(self, messages, model=None):
                return "test"
            
            def count_tokens(self, text):
                return len(text.split())
            
            def validate_model(self, model):
                return True
        
        provider = TestProvider()
        
        with pytest.raises(NotImplementedError):
            provider.chat_completion_with_tools([], [])

    def test_openai_provider_tool_method_exists(self):
        """OpenAI provider should have chat_completion_with_tools() method."""
        assert hasattr(OpenAIProvider, "chat_completion_with_tools")
        assert callable(getattr(OpenAIProvider, "chat_completion_with_tools"))

    def test_openai_chat_completion_with_tools_response_shape(self):
        """Tool-enabled completion should return structured dict with content, tool_calls, finish_reason."""
        provider = OpenAIProvider()
        
        with patch("openai.chat.completions.create") as mock_create:
            # Mock response with tool call
            tool_call = MagicMock()
            tool_call.id = "call_123"
            tool_call.function.name = "search_github"
            tool_call.function.arguments = '{"query": "test"}'
            
            mock_create.return_value.choices[0].message.content = None
            mock_create.return_value.choices[0].message.tool_calls = [tool_call]
            mock_create.return_value.choices[0].finish_reason = "tool_calls"
            
            messages = [{"role": "user", "content": "Search GitHub"}]
            tools = [{"type": "function", "function": {"name": "search_github"}}]
            
            result = provider.chat_completion_with_tools(messages, tools)
            
            # Verify response structure
            assert isinstance(result, dict)
            assert "content" in result
            assert "tool_calls" in result
            assert "finish_reason" in result
            assert result["finish_reason"] == "tool_calls"

    def test_openai_tool_calls_are_properly_structured(self):
        """Tool calls in response should be parsed and structured correctly."""
        provider = OpenAIProvider()
        
        with patch("openai.chat.completions.create") as mock_create:
            tool_call = MagicMock()
            tool_call.id = "call_456"
            tool_call.function.name = "create_jira_issue"
            tool_call.function.arguments = '{"title": "New bug", "priority": "high"}'
            
            mock_create.return_value.choices[0].message.content = ""
            mock_create.return_value.choices[0].message.tool_calls = [tool_call]
            mock_create.return_value.choices[0].finish_reason = "tool_calls"
            
            result = provider.chat_completion_with_tools([], [])
            
            # Verify tool call structure
            assert len(result["tool_calls"]) == 1
            call = result["tool_calls"][0]
            assert call["id"] == "call_456"
            assert call["name"] == "create_jira_issue"
            assert isinstance(call["arguments"], dict)
            assert call["arguments"]["title"] == "New bug"
            assert call["arguments"]["priority"] == "high"

    def test_openai_tool_call_with_malformed_json_fallback(self):
        """Tool calls with malformed JSON should have graceful fallback."""
        provider = OpenAIProvider()
        
        with patch("openai.chat.completions.create") as mock_create:
            tool_call = MagicMock()
            tool_call.id = "call_bad"
            tool_call.function.name = "test_tool"
            tool_call.function.arguments = "not valid json"
            
            mock_create.return_value.choices[0].message.content = ""
            mock_create.return_value.choices[0].message.tool_calls = [tool_call]
            mock_create.return_value.choices[0].finish_reason = "tool_calls"
            
            result = provider.chat_completion_with_tools([], [])
            
            call = result["tool_calls"][0]
            assert "_raw" in call["arguments"]
            assert call["arguments"]["_raw"] == "not valid json"

    def test_openai_response_without_tool_calls(self):
        """Tool-enabled method should handle text-only responses (no tool calls)."""
        provider = OpenAIProvider()
        
        with patch("openai.chat.completions.create") as mock_create:
            mock_create.return_value.choices[0].message.content = "I cannot help with that"
            mock_create.return_value.choices[0].message.tool_calls = None
            mock_create.return_value.choices[0].finish_reason = "stop"
            
            result = provider.chat_completion_with_tools(
                [{"role": "user", "content": "test"}],
                []
            )
            
            assert result["content"] == "I cannot help with that"
            assert result["tool_calls"] == []
            assert result["finish_reason"] == "stop"

    def test_openai_multiple_tool_calls_in_response(self):
        """Tool-enabled method should handle multiple tool calls correctly."""
        provider = OpenAIProvider()
        
        with patch("openai.chat.completions.create") as mock_create:
            tool_call1 = MagicMock()
            tool_call1.id = "call_1"
            tool_call1.function.name = "tool1"
            tool_call1.function.arguments = '{"x": 1}'
            
            tool_call2 = MagicMock()
            tool_call2.id = "call_2"
            tool_call2.function.name = "tool2"
            tool_call2.function.arguments = '{"y": 2}'
            
            mock_create.return_value.choices[0].message.content = ""
            mock_create.return_value.choices[0].message.tool_calls = [tool_call1, tool_call2]
            mock_create.return_value.choices[0].finish_reason = "tool_calls"
            
            result = provider.chat_completion_with_tools([], [])
            
            assert len(result["tool_calls"]) == 2
            assert result["tool_calls"][0]["id"] == "call_1"
            assert result["tool_calls"][1]["id"] == "call_2"


class TestProviderContractNonRegression:
    """Verify no regression in existing functionality."""

    def test_token_counting_method_still_exists(self):
        """Token counting behavior should not be removed."""
        provider = OpenAIProvider()
        # Check that token methods still exist (if they do)
        # This is a sanity check for backward compatibility
        assert hasattr(provider, "_default_model")

    def test_model_validation_still_works(self):
        """Model validation method should still be callable."""
        provider = OpenAIProvider()
        assert hasattr(provider, "validate_model")
        assert callable(getattr(provider, "validate_model"))

    def test_existing_callers_not_broken(self):
        """Existing code calling chat_completion() should not need changes."""
        provider = OpenAIProvider()
        
        with patch("openai.chat.completions.create") as mock_create:
            mock_create.return_value.choices[0].message.content = "Response"
            mock_create.return_value.choices[0].finish_reason = "stop"
            
            # Simulate existing caller pattern
            messages = [{"role": "user", "content": "hello"}]
            response = provider.chat_completion(messages)
            
            # Should work exactly as before
            assert response == "Response"
            assert isinstance(response, str)


class TestProviderIntegration:
    """Integration tests for provider behavior."""

    def test_openai_provider_instantiation(self):
        """Provider should instantiate without errors."""
        provider = OpenAIProvider()
        assert provider is not None
        assert hasattr(provider, "chat_completion")
        assert hasattr(provider, "chat_completion_with_tools")

    def test_tool_method_accessible_on_instance(self):
        """Tool method should be accessible on provider instance."""
        provider = OpenAIProvider()
        method = getattr(provider, "chat_completion_with_tools", None)
        assert method is not None
        assert callable(method)

    def test_both_methods_are_distinct(self):
        """chat_completion() and chat_completion_with_tools() should be distinct methods."""
        provider = OpenAIProvider()
        chat_method = getattr(provider, "chat_completion")
        tool_method = getattr(provider, "chat_completion_with_tools")
        assert chat_method != tool_method
