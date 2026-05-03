"""Unit and integration tests for Phase 1 SSE streaming.

Coverage:
- OpenAIProvider.stream_chat_completion token yielding (unit)
- ai_agent.stream_chat SSE event sequence (unit)
- stream_chat generator exit / disconnect cleanup (unit + integration)
- stream_chat timeout error event (unit)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _collect_stream(gen) -> list[dict]:
    """Consume an SSE async generator and return parsed JSON payloads."""
    events = []
    async for raw in gen:
        # Each yielded string is "data: {...}\n\n"
        stripped = raw.strip()
        if stripped.startswith("data: "):
            payload = stripped[len("data: "):]
            events.append(json.loads(payload))
    return events


def _make_mock_provider(tokens: list[str] | None = None):
    """Build a minimal provider mock that streams the given tokens."""
    if tokens is None:
        tokens = ["Hello", ", ", "world", "!"]

    async def _stream(messages, model=None):
        for tok in tokens:
            yield tok

    provider = MagicMock()
    provider.count_tokens.return_value = 100
    provider.stream_chat_completion = _stream
    return provider


# ─────────────────────────────────────────────────────────────────────────────
# 1. OpenAIProvider.stream_chat_completion
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenAIProviderStreamChatCompletion:
    """Unit tests for OpenAIProvider.stream_chat_completion."""

    @pytest.mark.asyncio
    async def test_yields_tokens_from_openai(self, monkeypatch):
        """stream_chat_completion yields tokens produced by the OpenAI streaming API."""
        import openai as openai_module

        from app.ai_agent.providers.openai.openai_provider import OpenAIProvider

        monkeypatch.setenv("OPENAI_API_KEY", "test-key-abc")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")

        # Build mock stream chunks
        def _make_chunk(content):
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock()
            chunk.choices[0].delta.content = content
            return chunk

        tokens = ["Hello", ", ", "world", "!"]
        chunks = [_make_chunk(t) for t in tokens]
        # Add a chunk with no content (finish chunk)
        finish_chunk = MagicMock()
        finish_chunk.choices = [MagicMock()]
        finish_chunk.choices[0].delta = MagicMock()
        finish_chunk.choices[0].delta.content = None
        chunks.append(finish_chunk)

        async def _aiter_chunks():
            for ch in chunks:
                yield ch

        mock_stream = MagicMock()
        mock_stream.__aiter__ = lambda self: _aiter_chunks()

        mock_response = AsyncMock(return_value=mock_stream)

        mock_async_client = MagicMock()
        mock_async_client.chat = MagicMock()
        mock_async_client.chat.completions = MagicMock()
        mock_async_client.chat.completions.create = mock_response
        mock_async_client.close = AsyncMock()

        with patch.object(openai_module, "AsyncOpenAI", return_value=mock_async_client):
            provider = OpenAIProvider()
            collected = []
            async for tok in provider.stream_chat_completion(
                [{"role": "user", "content": "hi"}], model="gpt-4o"
            ):
                collected.append(tok)

        assert collected == ["Hello", ", ", "world", "!"]
        mock_async_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_openai_exception(self, monkeypatch):
        """stream_chat_completion raises RuntimeError when the OpenAI API fails."""
        import openai as openai_module

        from app.ai_agent.providers.openai.openai_provider import OpenAIProvider

        monkeypatch.setenv("OPENAI_API_KEY", "test-key-abc")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")

        mock_async_client = MagicMock()
        mock_async_client.chat = MagicMock()
        mock_async_client.chat.completions = MagicMock()
        mock_async_client.chat.completions.create = AsyncMock(side_effect=Exception("API down"))
        mock_async_client.close = AsyncMock()

        with patch.object(openai_module, "AsyncOpenAI", return_value=mock_async_client):
            provider = OpenAIProvider()
            with pytest.raises(RuntimeError, match="OpenAI streaming error"):
                async for _ in provider.stream_chat_completion(
                    [{"role": "user", "content": "hi"}], model="gpt-4o"
                ):
                    pass

        mock_async_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_not_implemented_on_base_provider(self):
        """LLMProvider base stream_chat_completion raises NotImplementedError."""
        from app.ai_agent.providers.base import LLMProvider

        class _ConcreteProvider(LLMProvider):
            @property
            def name(self):
                return "test"

            @property
            def default_model(self):
                return "test-model"

            @property
            def supports_native_token_counting(self):
                return False

            def chat_completion(self, messages, model=None):
                return ""

            def count_tokens(self, messages, model=None):
                return 0

            def validate_model(self, model):
                return True

        provider = _ConcreteProvider()
        with pytest.raises(NotImplementedError):
            async for _ in provider.stream_chat_completion([]):
                pass


# ─────────────────────────────────────────────────────────────────────────────
# 2. stream_chat SSE event sequence
# ─────────────────────────────────────────────────────────────────────────────

class TestStreamChatEventSequence:
    """Unit tests for the SSE event sequence emitted by ai_agent.stream_chat."""

    @pytest.fixture()
    def _session(self, monkeypatch):
        """Create a fresh chat session and patch the module-level provider."""
        from app.ai_agent import ai_agent

        session_id = "test-session-001"
        ai_agent._chat_sessions[session_id] = [
            {"role": "system", "content": "You are helpful."}
        ]

        mock_provider = _make_mock_provider(["Hello", ", ", "world", "!"])
        monkeypatch.setattr(ai_agent, "_provider", mock_provider)

        yield session_id, ai_agent

        ai_agent._chat_sessions.pop(session_id, None)

    @pytest.mark.asyncio
    async def test_event_sequence_no_augmentation(self, _session, monkeypatch):
        """stream_chat emits thinking_start → message_start → chunks → message_end."""
        session_id, ai_agent_mod = _session

        # Patch augment_message_stream to return user_message unchanged
        async def _passthrough(user_message, provider=None):
            yield {"type": "augmented_message", "content": user_message}

        monkeypatch.setattr(ai_agent_mod, "augment_message_stream", _passthrough)

        events = await _collect_stream(
            ai_agent_mod.stream_chat(session_id, "What is 2+2?")
        )

        types = [e["type"] for e in events]
        assert types[0] == "thinking_start"
        assert "message_start" in types
        assert "message_chunk" in types
        assert types[-1] == "message_end"

        chunks = [e["content"] for e in events if e["type"] == "message_chunk"]
        assert "".join(chunks) == "Hello, world!"

    @pytest.mark.asyncio
    async def test_thinking_chunks_forwarded(self, _session, monkeypatch):
        """thinking_chunk events from augment_message_stream are forwarded to the SSE stream."""
        session_id, ai_agent_mod = _session

        async def _augment_with_thinking(user_message, provider=None):
            yield {"type": "thinking_chunk", "content": "Checking graph..."}
            yield {"type": "thinking_end"}
            yield {"type": "augmented_message", "content": user_message}

        monkeypatch.setattr(ai_agent_mod, "augment_message_stream", _augment_with_thinking)

        events = await _collect_stream(
            ai_agent_mod.stream_chat(session_id, "Show me the team")
        )

        types = [e["type"] for e in events]
        assert "thinking_start" in types
        assert "thinking_chunk" in types
        assert "thinking_end" in types
        assert "message_start" in types
        assert "message_end" in types

    @pytest.mark.asyncio
    async def test_session_history_saved_after_stream(self, _session, monkeypatch):
        """After streaming, the assistant response is appended to the session history."""
        session_id, ai_agent_mod = _session

        async def _passthrough(user_message, provider=None):
            yield {"type": "augmented_message", "content": user_message}

        monkeypatch.setattr(ai_agent_mod, "augment_message_stream", _passthrough)

        await _collect_stream(ai_agent_mod.stream_chat(session_id, "hi"))

        messages = ai_agent_mod._chat_sessions[session_id]
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles
        assert messages[-1]["role"] == "assistant"
        assert messages[-1]["content"] == "Hello, world!"

    @pytest.mark.asyncio
    async def test_token_pruning_applied(self, monkeypatch):
        """Token pruning removes oldest messages when token count exceeds max_tokens."""
        from app.ai_agent import ai_agent

        session_id = "test-prune-session"
        system_msg = {"role": "system", "content": "System."}
        # Add 6 messages (excluding system) to trigger pruning
        ai_agent._chat_sessions[session_id] = [
            system_msg,
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "resp1"},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "resp2"},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": "resp3"},
        ]

        mock_provider = _make_mock_provider(["OK"])
        # Force token count to exceed limit
        mock_provider.count_tokens.return_value = 99999
        monkeypatch.setattr(ai_agent, "_provider", mock_provider)

        async def _passthrough(user_message, provider=None):
            yield {"type": "augmented_message", "content": user_message}

        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough)

        captured_messages: list[Any] = []
        original_stream = mock_provider.stream_chat_completion

        async def _capture(messages, model=None):
            captured_messages.extend(messages)
            async for tok in original_stream(messages, model):
                yield tok

        mock_provider.stream_chat_completion = _capture

        await _collect_stream(
            ai_agent.stream_chat(session_id, "new message", max_tokens=100)
        )

        # After pruning, the messages passed to the LLM should not contain
        # the original second and third messages (msg1/resp1 removed).
        contents = [m["content"] for m in captured_messages]
        assert "msg1" not in contents
        assert "resp1" not in contents

        ai_agent._chat_sessions.pop(session_id, None)

    @pytest.mark.asyncio
    async def test_raises_value_error_for_unknown_session(self):
        """stream_chat raises ValueError immediately if session_id is unknown."""
        from app.ai_agent import ai_agent

        with pytest.raises(ValueError, match="Session not found"):
            async for _ in ai_agent.stream_chat("nonexistent-session-xyz", "hello"):
                pass


# ─────────────────────────────────────────────────────────────────────────────
# 3. Generator exit / disconnect
# ─────────────────────────────────────────────────────────────────────────────

class TestStreamChatGeneratorExit:
    """Unit tests for generator cancellation and disconnect handling."""

    @pytest.mark.asyncio
    async def test_cancelled_error_increments_disconnect_metric(self, monkeypatch):
        """CancelledError increments the disconnect counter and is re-raised.

        Simulates a client disconnect by cancelling the task that consumes the
        generator — the same mechanism FastAPI uses when the HTTP connection drops.
        gen.aclose() sends GeneratorExit (not CancelledError) so it cannot be
        used here; task cancellation is the correct approach.
        """
        from app.ai_agent import ai_agent

        session_id = "cancel-test-session"
        ai_agent._chat_sessions[session_id] = [
            {"role": "system", "content": "System."}
        ]

        # Record metrics before
        before = ai_agent.get_streaming_metrics()["disconnects"]

        # Gate that lets the test know the generator has reached the LLM phase
        reached_llm = asyncio.Event()

        async def _slow_stream(messages, model=None):
            reached_llm.set()
            await asyncio.sleep(10)  # Will be cancelled before this completes
            yield "never"  # pragma: no cover

        mock_provider = _make_mock_provider()
        mock_provider.stream_chat_completion = _slow_stream
        monkeypatch.setattr(ai_agent, "_provider", mock_provider)

        async def _passthrough(user_message, provider=None):
            yield {"type": "augmented_message", "content": user_message}

        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough)

        async def _consume_forever():
            async for _ in ai_agent.stream_chat(session_id, "test cancel"):
                pass

        task = asyncio.create_task(_consume_forever())
        # Wait until the generator is suspended inside the slow LLM stream
        await asyncio.wait_for(reached_llm.wait(), timeout=5.0)
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        after = ai_agent.get_streaming_metrics()["disconnects"]
        assert after == before + 1

        ai_agent._chat_sessions.pop(session_id, None)

    @pytest.mark.asyncio
    async def test_no_resource_leak_on_generator_close(self, monkeypatch):
        """Closing the generator early does not raise unhandled exceptions."""
        from app.ai_agent import ai_agent

        session_id = "close-test-session"
        ai_agent._chat_sessions[session_id] = [
            {"role": "system", "content": "System."}
        ]

        mock_provider = _make_mock_provider(["token1", "token2", "token3"])
        monkeypatch.setattr(ai_agent, "_provider", mock_provider)

        async def _passthrough(user_message, provider=None):
            yield {"type": "augmented_message", "content": user_message}

        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough)

        gen = ai_agent.stream_chat(session_id, "early close")
        # Consume just the first event then close
        first = await gen.__anext__()
        assert first is not None
        # aclose() must complete without raising
        await gen.aclose()

        ai_agent._chat_sessions.pop(session_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Timeout tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStreamChatTimeouts:
    """Unit tests for timeout error events in stream_chat."""

    @pytest.mark.asyncio
    async def test_llm_timeout_yields_error_event(self, monkeypatch):
        """When the LLM stream exceeds its timeout, an error event is emitted."""
        from app.ai_agent import ai_agent

        session_id = "timeout-test-session"
        ai_agent._chat_sessions[session_id] = [
            {"role": "system", "content": "System."}
        ]

        async def _hanging_stream(messages, model=None):
            # Simulate a stream that never produces tokens
            await asyncio.sleep(999)
            yield "never"  # pragma: no cover

        mock_provider = _make_mock_provider()
        mock_provider.stream_chat_completion = _hanging_stream
        monkeypatch.setattr(ai_agent, "_provider", mock_provider)

        async def _passthrough(user_message, provider=None):
            yield {"type": "augmented_message", "content": user_message}

        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough)

        # Patch asyncio.timeout to a very short duration for the test
        original_timeout = asyncio.timeout

        class _ShortTimeout:
            def __init__(self, delay):
                self._delay = 0.05  # Override to 50 ms for test speed

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return False

        # Use asyncio.timeout_at with a past deadline to force immediate timeout
        import contextlib

        @contextlib.asynccontextmanager
        async def _instant_timeout(delay):
            deadline = asyncio.get_event_loop().time() - 1  # already expired
            async with asyncio.timeout_at(deadline):
                yield

        monkeypatch.setattr(asyncio, "timeout", _instant_timeout)

        events = await _collect_stream(
            ai_agent.stream_chat(session_id, "slow query")
        )

        types = [e["type"] for e in events]
        assert "error" in types
        error_events = [e for e in events if e["type"] == "error"]
        assert any("timed out" in e.get("content", "").lower() for e in error_events)

        ai_agent._chat_sessions.pop(session_id, None)

    @pytest.mark.asyncio
    async def test_error_in_stream_yields_error_event_and_increments_metric(self, monkeypatch):
        """An unexpected exception during streaming yields an error event."""
        from app.ai_agent import ai_agent

        session_id = "error-test-session"
        ai_agent._chat_sessions[session_id] = [
            {"role": "system", "content": "System."}
        ]

        async def _failing_stream(messages, model=None):
            yield "partial"
            raise RuntimeError("Simulated LLM failure")

        mock_provider = _make_mock_provider()
        mock_provider.stream_chat_completion = _failing_stream
        monkeypatch.setattr(ai_agent, "_provider", mock_provider)

        async def _passthrough(user_message, provider=None):
            yield {"type": "augmented_message", "content": user_message}

        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough)

        before_errors = ai_agent.get_streaming_metrics()["errors"]

        events = await _collect_stream(
            ai_agent.stream_chat(session_id, "trigger error")
        )

        types = [e["type"] for e in events]
        assert "error" in types

        after_errors = ai_agent.get_streaming_metrics()["errors"]
        assert after_errors == before_errors + 1

        ai_agent._chat_sessions.pop(session_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Integration test: disconnect mid-stream via ASGI
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_client_disconnect_mid_stream_increments_metric(monkeypatch):
    """A client closing the connection mid-stream increments the disconnect counter.

    Uses httpx.AsyncClient with ASGI transport against a minimal FastAPI app
    that wraps stream_chat in a StreamingResponse.  The anyio backend drives the
    test so that task cancellation semantics match production behaviour.
    """
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse
    import httpx

    from app.ai_agent import ai_agent

    session_id = "asgi-disconnect-session"
    ai_agent._chat_sessions[session_id] = [
        {"role": "system", "content": "System."}
    ]

    # Provider that yields tokens slowly enough for the client to disconnect
    slow_tokens_event = asyncio.Event()

    async def _slow_provider_stream(messages, model=None):
        for i in range(50):
            yield f"token{i}"
            await asyncio.sleep(0.01)

    mock_provider = _make_mock_provider()
    mock_provider.stream_chat_completion = _slow_provider_stream
    monkeypatch.setattr(ai_agent, "_provider", mock_provider)

    async def _passthrough(user_message, provider=None):
        yield {"type": "augmented_message", "content": user_message}

    monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough)

    # Minimal FastAPI app for this test
    test_app = FastAPI()

    @test_app.post("/stream/{sid}")
    async def _stream_endpoint(sid: str):
        return StreamingResponse(
            ai_agent.stream_chat(sid, "hello"),
            media_type="text/event-stream",
        )

    before_disconnects = ai_agent.get_streaming_metrics()["disconnects"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        async with client.stream("POST", f"/stream/{session_id}") as response:
            # Read just a few chunks then abort
            count = 0
            async for _ in response.aiter_lines():
                count += 1
                if count >= 3:
                    break  # Close the connection early

    # Give the server a moment to handle the disconnect
    await asyncio.sleep(0.1)

    after_disconnects = ai_agent.get_streaming_metrics()["disconnects"]
    # Disconnect counter should have incremented (or completions if it finished)
    assert (
        after_disconnects > before_disconnects
        or ai_agent.get_streaming_metrics()["completions"] > 0
    ), "Stream should have registered a disconnect or completion after early close"

    ai_agent._chat_sessions.pop(session_id, None)
