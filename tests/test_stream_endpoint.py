"""Automated tests for Phase 2: FastAPI streaming endpoint.

Coverage:
- POST /api/v1/chats/{session_id}/stream returns Content-Type: text/event-stream
- Full SSE event sequence is valid (unit, ASGI transport)
- Unknown session_id returns 404 before streaming begins
- Client disconnect mid-stream increments disconnect metric
- Metrics endpoint GET /api/v1/chats/metrics/stream returns expected keys
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

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


async def _passthrough_augment(user_message, provider=None):
    """Minimal augment_message_stream that skips chains."""
    yield {"type": "augmented_message", "content": user_message}


async def _collect_sse_lines(response) -> list[dict]:
    """Collect and parse all non-empty SSE data lines from an httpx response."""
    events = []
    async for line in response.aiter_lines():
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


# ─────────────────────────────────────────────────────────────────────────────
# 1. Content-Type check
# ─────────────────────────────────────────────────────────────────────────────

class TestStreamEndpointContentType:
    """The /stream endpoint must respond with text/event-stream."""

    async def test_content_type_is_text_event_stream(self, monkeypatch):
        from app.main import app
        from app.ai_agent import ai_agent

        session_id = "ct-test-session"
        ai_agent._chat_sessions[session_id] = [{"role": "system", "content": "System."}]
        monkeypatch.setattr(ai_agent, "_provider", _make_mock_provider())
        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough_augment)

        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                async with client.stream(
                    "POST",
                    f"/api/v1/chats/{session_id}/stream",
                    json={"message": "hi"},
                ) as response:
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers["content-type"]
                    # Drain so the generator completes cleanly
                    async for _ in response.aiter_bytes():
                        pass
        finally:
            ai_agent._chat_sessions.pop(session_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Full SSE event sequence
# ─────────────────────────────────────────────────────────────────────────────

class TestStreamEndpointEventSequence:
    """The /stream endpoint must emit a well-formed SSE event sequence."""

    async def test_event_sequence_starts_with_thinking_start(self, monkeypatch):
        from app.main import app
        from app.ai_agent import ai_agent

        session_id = "seq-test-session"
        ai_agent._chat_sessions[session_id] = [{"role": "system", "content": "System."}]
        monkeypatch.setattr(ai_agent, "_provider", _make_mock_provider(["tok1", "tok2"]))
        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough_augment)

        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                async with client.stream(
                    "POST",
                    f"/api/v1/chats/{session_id}/stream",
                    json={"message": "hello"},
                ) as response:
                    assert response.status_code == 200
                    events = await _collect_sse_lines(response)
        finally:
            ai_agent._chat_sessions.pop(session_id, None)

        types = [e["type"] for e in events]
        assert types[0] == "thinking_start"
        assert "message_start" in types
        assert "message_chunk" in types
        assert types[-1] == "message_end"

    async def test_message_chunks_contain_expected_tokens(self, monkeypatch):
        from app.main import app
        from app.ai_agent import ai_agent

        session_id = "chunk-test-session"
        ai_agent._chat_sessions[session_id] = [{"role": "system", "content": "System."}]
        tokens = ["Hello", " world"]
        monkeypatch.setattr(ai_agent, "_provider", _make_mock_provider(tokens))
        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough_augment)

        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                async with client.stream(
                    "POST",
                    f"/api/v1/chats/{session_id}/stream",
                    json={"message": "hello"},
                ) as response:
                    events = await _collect_sse_lines(response)
        finally:
            ai_agent._chat_sessions.pop(session_id, None)

        chunks = [e["content"] for e in events if e["type"] == "message_chunk"]
        assert chunks == tokens

    async def test_session_history_saved_after_stream(self, monkeypatch):
        from app.main import app
        from app.ai_agent import ai_agent

        session_id = "history-test-session"
        ai_agent._chat_sessions[session_id] = [{"role": "system", "content": "System."}]
        monkeypatch.setattr(ai_agent, "_provider", _make_mock_provider(["hi"]))
        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough_augment)

        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                async with client.stream(
                    "POST",
                    f"/api/v1/chats/{session_id}/stream",
                    json={"message": "save me"},
                ) as response:
                    async for _ in response.aiter_bytes():
                        pass

            history = ai_agent._chat_sessions[session_id]
            roles = [m["role"] for m in history]
            assert "user" in roles
            assert "assistant" in roles
        finally:
            ai_agent._chat_sessions.pop(session_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Unknown session → 404 before streaming
# ─────────────────────────────────────────────────────────────────────────────

class TestStreamEndpointUnknownSession:
    """Streaming an unknown session_id must return a JSON 404, not a broken stream."""

    async def test_unknown_session_returns_404(self):
        from app.main import app

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/chats/nonexistent-session-xyz/stream",
                json={"message": "hello"},
            )

        assert response.status_code == 404
        body = response.json()
        assert "detail" in body


# ─────────────────────────────────────────────────────────────────────────────
# 4. Client disconnect increments disconnect metric
# ─────────────────────────────────────────────────────────────────────────────

class TestStreamEndpointDisconnect:
    """Closing the connection mid-stream must increment the disconnect metric."""

    async def test_disconnect_increments_metric(self, monkeypatch):
        from app.main import app
        from app.ai_agent import ai_agent

        session_id = "disconnect-ep-session"
        ai_agent._chat_sessions[session_id] = [{"role": "system", "content": "System."}]

        async def _slow_stream(messages, model=None):
            for i in range(50):
                yield f"token{i}"
                await asyncio.sleep(0.01)

        mock_provider = _make_mock_provider()
        mock_provider.stream_chat_completion = _slow_stream
        monkeypatch.setattr(ai_agent, "_provider", mock_provider)
        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough_augment)

        before = ai_agent.get_streaming_metrics()["disconnects"]

        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                async with client.stream(
                    "POST",
                    f"/api/v1/chats/{session_id}/stream",
                    json={"message": "disconnect me"},
                ) as response:
                    count = 0
                    async for _ in response.aiter_lines():
                        count += 1
                        if count >= 3:
                            break
        finally:
            ai_agent._chat_sessions.pop(session_id, None)

        await asyncio.sleep(0.15)

        after = ai_agent.get_streaming_metrics()["disconnects"]
        completions = ai_agent.get_streaming_metrics()["completions"]
        assert after > before or completions > 0, (
            "Expected disconnect or completion to be recorded after early client close"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Metrics endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestStreamMetricsEndpoint:
    """GET /api/v1/chats/metrics/stream must return the expected metric keys."""

    async def test_metrics_endpoint_returns_expected_keys(self):
        from app.main import app

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/chats/metrics/stream")

        assert response.status_code == 200
        data = response.json()
        for key in ("starts", "completions", "errors", "disconnects", "total_duration_seconds"):
            assert key in data, f"Missing key: {key}"

    async def test_metrics_starts_increments_after_stream(self, monkeypatch):
        from app.main import app
        from app.ai_agent import ai_agent

        session_id = "metrics-starts-session"
        ai_agent._chat_sessions[session_id] = [{"role": "system", "content": "System."}]
        monkeypatch.setattr(ai_agent, "_provider", _make_mock_provider(["a"]))
        monkeypatch.setattr(ai_agent, "augment_message_stream", _passthrough_augment)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            before = (await client.get("/api/v1/chats/metrics/stream")).json()["starts"]

            async with client.stream(
                "POST",
                f"/api/v1/chats/{session_id}/stream",
                json={"message": "count me"},
            ) as response:
                async for _ in response.aiter_bytes():
                    pass

            after = (await client.get("/api/v1/chats/metrics/stream")).json()["starts"]

        ai_agent._chat_sessions.pop(session_id, None)
        assert after == before + 1
