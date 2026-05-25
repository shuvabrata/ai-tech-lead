# Custom LLM Provider Development Guide

This guide explains how to implement a custom LLM provider for the Work Behavior Analytics AI system. A custom provider lets you plug in any LLM backend — a local model, a self-hosted API, an enterprise gateway, or a third-party service — without modifying core application code.

---

## Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Required Interface](#2-required-interface)
3. [Optional Extensions](#3-optional-extensions)
   - 3.1 [Streaming (`stream_chat_completion`)](#31-streaming-stream_chat_completion)
   - 3.2 [Tool Calling (`chat_completion_with_tools`)](#32-tool-calling-chat_completion_with_tools)
4. [Token Counting](#4-token-counting)
5. [Worked Example — Minimal Provider](#5-worked-example--minimal-provider)
6. [Worked Example — Full Streaming Provider](#6-worked-example--full-streaming-provider)
7. [Registering Your Provider](#7-registering-your-provider)
8. [Environment Variables](#8-environment-variables)
9. [SSE Metadata Event](#9-sse-metadata-event)
10. [Testing Your Provider](#10-testing-your-provider)
11. [Compliance Checklist](#11-compliance-checklist)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Architecture Overview

```
Client (browser)
     │  POST /api/v1/chats/{session_id}/stream
     ▼
FastAPI router  ──►  ai_agent.stream_chat()
                          │
                          ├──►  chains.augment_message_stream()   [adds context]
                          │
                          └──►  LLMProvider.stream_chat_completion()   ◄── YOUR CODE
                                         │
                                 yields token strings
                                         │
                          SSE events: thinking_start / thinking_chunk / thinking_end /
                                      message_start / message_chunk / metadata / message_end
                          ▼
                     Dash UI (stream-bridge.js)
```

All LLM providers implement the abstract base class `LLMProvider` defined in:

```
src/app/ai_agent/providers/base.py
```

The factory (`src/app/ai_agent/providers/factory.py`) selects your provider at startup based on the `LLM_PROVIDER` environment variable, caches the instance, and injects it throughout the application.

---

## 2. Required Interface

Inherit from `LLMProvider` and implement all abstract members:

```python
from typing import Any, Dict, List, Optional
from app.ai_agent.providers.base import LLMProvider


class MyProvider(LLMProvider):

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        """Lowercase identifier used in logs and the metadata SSE event."""
        return "my_provider"

    @property
    def default_model(self) -> str:
        """Default model name when no model is specified per-request."""
        return "my-model-v1"

    @property
    def supports_native_token_counting(self) -> bool:
        """True if count_tokens() returns exact counts; False for estimates."""
        return False

    # ── Chat completion (blocking) ───────────────────────────────────────────

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        """Send messages and return the complete response as a string.

        Args:
            messages: Conversation history.
                      Format: [{"role": "system|user|assistant", "content": "..."}]
            model: Override the default model. None → use default_model.

        Returns:
            The assistant's reply as a plain string.

        Raises:
            RuntimeError: On API/network failure.
            ValueError: If the requested model is not supported.
        """
        model_to_use = model or self.default_model
        # ... call your API here ...
        return response_text

    # ── Token counting ───────────────────────────────────────────────────────

    def count_tokens(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> int:
        """Return token count for the message list.

        If your backend does not expose token counts, use the built-in
        character-based estimator (see Section 4).
        """
        return self._estimate_tokens_from_text(
            " ".join(m["content"] for m in messages)
        )

    # ── Model validation ─────────────────────────────────────────────────────

    def validate_model(self, model: str) -> bool:
        """Return True if the model name is accepted by your backend."""
        return model in {"my-model-v1", "my-model-v2"}
```

> **Note on `chat_completion`**: The system calls this method for non-streaming paths (CLI, tests, and fallback). It is synchronous and must return the full response before returning.

---

## 3. Optional Extensions

### 3.1 Streaming (`stream_chat_completion`)

Streaming is required for the `/stream` SSE endpoint. Without it, hitting that endpoint raises:

```
NotImplementedError: Provider 'my_provider' does not implement streaming chat completions
```

and the browser receives a `stream_error` SSE event.

**Signature:**

```python
async def stream_chat_completion(
    self,
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
):
    """Async generator that yields token strings as they are produced.

    Yields:
        str: Individual token or token-group strings. Yield as granularly
             as your API allows — the system reassembles them for the UI.

    Raises:
        RuntimeError: On connection or API failure.
        ValueError: If the requested model is not supported.
    """
```

**Contract:**

| Requirement | Detail |
|---|---|
| Must be `async def` | The system calls it inside an async context |
| Must be an async generator | Use `yield` to emit tokens |
| Yield token strings | Raw text fragments; no wrapping or SSE framing |
| Handle `asyncio.CancelledError` | Client disconnect — release resources in `finally` |
| Raise `RuntimeError` on API failure | Caught by `stream_chat` and forwarded as an `error` SSE event (`{"type": "error", "content": "..."}`) |

See [Section 6](#6-worked-example--full-streaming-provider) for a complete implementation.

---

### 3.2 Tool Calling (`chat_completion_with_tools`)

Required when MCP (Model Context Protocol) tool orchestration is active. Without it, MCP chains fall back to non-tool augmentation.

**Signature:**

```python
def chat_completion_with_tools(
    self,
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: Optional[str] = None,
) -> Dict[str, Any]:
```

**Return value must include these keys:**

```python
{
    "content": str,          # Assistant text (may be empty when tool_calls is non-empty)
    "tool_calls": [          # List of tool calls requested by the model
        {
            "id": str,           # Unique call ID for tool result routing
            "name": str,         # Tool name as declared in the tools list
            "arguments": dict,   # Parsed JSON arguments
        }
    ],
    "finish_reason": str | None,  # e.g. "stop", "tool_calls", or None
}
```

The `tools` parameter follows the OpenAI function-calling schema (JSON Schema objects). If your backend uses a different schema, translate inside this method — the caller always passes OpenAI-format tools.

---

## 4. Token Counting

The system uses `count_tokens()` to manage chat history size and to populate the `tokens` field in the metadata SSE event.

**Option A — Estimation (no extra dependency):**

The base class provides `_estimate_tokens_from_text(text: str) -> int` which approximates `len(text) / 4`. Use it when your backend does not expose token counts:

```python
def count_tokens(self, messages, model=None):
    combined = " ".join(m["content"] for m in messages)
    return self._estimate_tokens_from_text(combined)
```

Set `supports_native_token_counting = False` so the system knows counts are approximate.

**Option B — tiktoken (accurate, OpenAI-compatible tokenizers):**

```python
import tiktoken

def count_tokens(self, messages, model=None):
    enc = tiktoken.encoding_for_model("gpt-4")   # or your model's encoding
    total = sum(len(enc.encode(m["content"])) for m in messages)
    return total
```

Set `supports_native_token_counting = True`.

**Option C — API-reported counts:**

Some APIs return token usage in the response. Cache the last reported value and return it here:

```python
def count_tokens(self, messages, model=None):
    return self._last_reported_token_count or self._estimate_tokens_from_text(
        " ".join(m["content"] for m in messages)
    )
```

---

## 5. Worked Example — Minimal Provider

A non-streaming provider that wraps an HTTP API via `requests`:

```python
"""Minimal custom LLM provider — non-streaming."""

import os
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

from app.ai_agent.providers.base import LLMProvider
from common.logger import logger


class CustomProvider(LLMProvider):
    """Minimal provider for a generic HTTP chat completions API."""

    SUPPORTED_MODELS = {"chat-v1", "chat-v2"}

    def __init__(self):
        load_dotenv()
        self._token = os.environ["CUSTOM_API_TOKEN"]
        self._base_url = os.getenv("CUSTOM_API_BASE_URL", "https://my-llm-api.internal")
        self._default_model = os.getenv("LLM_MODEL", "chat-v1")
        logger.info("CustomProvider initialized, model=%s", self._default_model)

    @property
    def name(self) -> str:
        return "custom"

    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def supports_native_token_counting(self) -> bool:
        return False

    def chat_completion(self, messages, model=None) -> str:
        model_to_use = model or self._default_model
        if not self.validate_model(model_to_use):
            raise ValueError(f"Unsupported model: {model_to_use}")
        try:
            response = requests.post(
                f"{self._base_url}/v1/chat",
                json={"model": model_to_use, "messages": messages},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=60,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error("CustomProvider API error: %s", e)
            raise RuntimeError(f"Custom API error: {e}") from e

    def count_tokens(self, messages, model=None) -> int:
        combined = " ".join(m["content"] for m in messages)
        return self._estimate_tokens_from_text(combined)

    def validate_model(self, model: str) -> bool:
        return model in self.SUPPORTED_MODELS
```

---

## 6. Worked Example — Full Streaming Provider

A streaming provider using `httpx` for async HTTP:

```python
"""Full streaming custom LLM provider."""

import asyncio
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from app.ai_agent.providers.base import LLMProvider
from common.logger import logger


class CustomProvider(LLMProvider):
    """Streaming-capable provider for a generic Server-Sent Events chat API."""

    SUPPORTED_MODELS = {"chat-v1", "chat-v2"}

    def __init__(self):
        load_dotenv()
        self._token = os.environ["CUSTOM_API_TOKEN"]
        self._base_url = os.getenv("CUSTOM_API_BASE_URL", "https://my-llm-api.internal")
        self._default_model = os.getenv("LLM_MODEL", "chat-v1")
        logger.info("CustomProvider initialized, model=%s", self._default_model)

    @property
    def name(self) -> str:
        return "custom"

    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def supports_native_token_counting(self) -> bool:
        return False

    # ── Non-streaming (required) ─────────────────────────────────────────────

    def chat_completion(self, messages: List[Dict[str, str]], model=None) -> str:
        import requests  # sync fallback

        model_to_use = model or self._default_model
        if not self.validate_model(model_to_use):
            raise ValueError(f"Unsupported model: {model_to_use}")
        try:
            response = requests.post(
                f"{self._base_url}/v1/chat",
                json={"model": model_to_use, "messages": messages},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=60,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            raise RuntimeError(f"Custom API error: {e}") from e

    # ── Streaming (optional, required for /stream endpoint) ──────────────────

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Async generator — yields token strings from a streaming API response."""
        model_to_use = model or self._default_model
        if not self.validate_model(model_to_use):
            raise ValueError(f"Unsupported model: {model_to_use}")

        async with httpx.AsyncClient(timeout=180) as client:
            try:
                logger.debug(
                    "Starting streaming request, model=%s, messages=%s",
                    model_to_use, len(messages),
                )
                async with client.stream(
                    "POST",
                    f"{self._base_url}/v1/chat/stream",
                    json={"model": model_to_use, "messages": messages, "stream": True},
                    headers={"Authorization": f"Bearer {self._token}"},
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        payload = line[6:]  # strip "data: "
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                            token = chunk["choices"][0]["delta"].get("content", "")
                            if token:
                                yield token
                        except (KeyError, json.JSONDecodeError):
                            continue
            except asyncio.CancelledError:
                # Client disconnected — normal path, let the context manager clean up
                logger.debug("Stream cancelled (client disconnected)")
                raise
            except Exception as e:
                logger.error("CustomProvider streaming error: %s", e)
                raise RuntimeError(f"Custom streaming error: {e}") from e

    # ── Tool calling (optional, required for MCP) ────────────────────────────

    def chat_completion_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        import requests  # sync

        model_to_use = model or self._default_model
        if not self.validate_model(model_to_use):
            raise ValueError(f"Unsupported model: {model_to_use}")
        try:
            response = requests.post(
                f"{self._base_url}/v1/chat",
                json={"model": model_to_use, "messages": messages, "tools": tools},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            content = (message.get("content") or "").strip()
            raw_calls = message.get("tool_calls") or []
            tool_calls = [
                {
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": json.loads(tc["function"].get("arguments", "{}")),
                }
                for tc in raw_calls
            ]
            return {
                "content": content,
                "tool_calls": tool_calls,
                "finish_reason": data["choices"][0].get("finish_reason"),
            }
        except Exception as e:
            logger.error("CustomProvider tool-calling error: %s", e)
            raise RuntimeError(f"Custom tool-calling error: {e}") from e

    # ── Token counting ────────────────────────────────────────────────────────

    def count_tokens(self, messages: List[Dict[str, str]], model=None) -> int:
        combined = " ".join(m["content"] for m in messages)
        return self._estimate_tokens_from_text(combined)

    def validate_model(self, model: str) -> bool:
        return model in self.SUPPORTED_MODELS
```

---

## 7. Registering Your Provider

**Step 1 — Place your class here:**

```
src/app/ai_agent/providers/custom/
├── __init__.py                     ← must export CustomProvider
└── custom_provider.py              ← your implementation
```

**Step 2 — Export from `__init__.py`:**

```python
# src/app/ai_agent/providers/custom/__init__.py
from .custom_provider import CustomProvider

__all__ = ["CustomProvider"]
```

**Step 3 — Set environment variables (see Section 8).**

The factory (`src/app/ai_agent/providers/factory.py`) already handles `LLM_PROVIDER=custom`:

```python
elif provider_name == "custom":
    from app.ai_agent.providers.custom import CustomProvider
    provider = CustomProvider()
```

No changes to `factory.py` are needed.

---

## 8. Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Yes | Must be `custom` to activate your provider |
| `LLM_MODEL` | No | Override the default model name. Falls back to your `default_model` property |
| `CUSTOM_API_TOKEN` | Recommended | API token passed to your backend. Access via `os.environ["CUSTOM_API_TOKEN"]` |
| `CUSTOM_API_BASE_URL` | No | Base URL for your API. Hardcode a sensible default if you own the backend |
| `MAX_TOKENS` | No | Chat history token budget. Default: `16000`. Affects when old messages are pruned |

Example `.env`:

```env
LLM_PROVIDER=custom
LLM_MODEL=chat-v2
CUSTOM_API_TOKEN=sk-my-secret-token
CUSTOM_API_BASE_URL=https://my-llm-api.internal
MAX_TOKENS=32000
DATABASE_URL=postgresql+asyncpg://wba:wba@localhost:5432/wba
```

---

## 9. SSE Metadata Event

After every streaming response the system emits a `metadata` SSE event before `message_end`. Your provider's `name` and `count_tokens()` result feed directly into this payload:

```json
{
  "type": "metadata",
  "content": {
    "tokens": {
      "prompt": 1240,
      "completion": 87,
      "total": 1327
    },
    "duration_seconds": 3.41,
    "model": "chat-v2",
    "sources": {
      "neo4j": true,
      "neo4j_query": "MATCH (p:Person)-[:WORKS_ON]->(proj:Project) ...",
      "mcp_tools": ["jira_search", "github_list_prs"]
    }
  }
}
```

The UI renders this as a compact info bar beneath each assistant message. No action is needed from your provider to support this — the system builds it automatically. However, a more accurate `count_tokens()` implementation gives users better token budget visibility.

---

## 10. Testing Your Provider

### Unit test — required interface

```python
import pytest
from app.ai_agent.providers.custom import CustomProvider


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("CUSTOM_API_TOKEN", "test-token")
    monkeypatch.setenv("CUSTOM_API_BASE_URL", "https://mock-api.test")
    return CustomProvider()


def test_provider_name(provider):
    assert provider.name == "custom"


def test_default_model(provider):
    assert provider.default_model != ""


def test_validate_model_returns_bool(provider):
    result = provider.validate_model("chat-v1")
    assert isinstance(result, bool)


def test_count_tokens_returns_int(provider):
    messages = [{"role": "user", "content": "Hello world"}]
    count = provider.count_tokens(messages)
    assert isinstance(count, int)
    assert count > 0
```

### Integration test — streaming

```python
import pytest


@pytest.mark.asyncio
async def test_stream_yields_strings(provider, httpx_mock):
    # Mock your streaming endpoint to return SSE lines
    httpx_mock.add_response(
        text='data: {"choices":[{"delta":{"content":"Hello"}}]}\ndata: [DONE]\n',
        headers={"content-type": "text/event-stream"},
    )
    messages = [{"role": "user", "content": "Say hello"}]
    tokens = []
    async for token in provider.stream_chat_completion(messages):
        tokens.append(token)
    assert tokens == ["Hello"]


@pytest.mark.asyncio
async def test_stream_raises_on_api_error(provider, httpx_mock):
    httpx_mock.add_response(status_code=500)
    with pytest.raises(RuntimeError, match="Custom streaming error"):
        async for _ in provider.stream_chat_completion([{"role": "user", "content": "hi"}]):
            pass
```

### Smoke test against a live backend

```bash
source .venv/bin/activate
LLM_PROVIDER=custom CUSTOM_API_TOKEN=sk-... uvicorn app.main:app --reload

# Non-streaming
curl -s http://localhost:8000/api/health

# Streaming (watch SSE events in terminal)
curl -N -X POST http://localhost:8000/api/v1/chats/test-session/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Who is working on the auth service?"}'
```

---

## 11. Compliance Checklist

Before submitting or deploying your provider, verify:

- [ ] Inherits from `app.ai_agent.providers.base.LLMProvider`
- [ ] `name` returns a non-empty lowercase string
- [ ] `default_model` returns a valid model name for your backend
- [ ] `chat_completion` returns a plain string and raises `RuntimeError` on failure
- [ ] `count_tokens` returns a positive integer
- [ ] `validate_model` returns `True`/`False` without raising
- [ ] `CustomProvider` is exported from `custom/__init__.py`
- [ ] `LLM_PROVIDER=custom` selects your provider via the factory
- [ ] **If streaming is needed**: `stream_chat_completion` is `async def`, uses `yield`, handles `asyncio.CancelledError` in `finally`
- [ ] **If MCP tools are needed**: `chat_completion_with_tools` returns `content`, `tool_calls`, and `finish_reason` keys
- [ ] Unit tests pass: `pytest tests/ -k custom`

---

## 12. Troubleshooting

### `ImportError: cannot import name 'CustomProvider'`

The factory imports `from app.ai_agent.providers.custom import CustomProvider`. Ensure:
- Your class is named exactly `CustomProvider`
- It is re-exported in `custom/__init__.py`

### `NotImplementedError: Provider 'custom' does not implement streaming chat completions`

Your class does not override `stream_chat_completion`. Implement it as an `async def` generator (see Section 3.1).

### Stream starts but stops immediately with no tokens

Your `stream_chat_completion` is not using `yield`. A method with `return` instead of `yield` is not a generator. Check that at least one code path executes `yield token`.

### `asyncio.CancelledError` appearing in logs as an error

This is normal when a browser tab is closed mid-stream. Do not catch and suppress it — re-raise it or let it propagate. Use `finally` to release resources.

### Token count is always 0

`_estimate_tokens_from_text("")` returns 0. Ensure you are joining message content correctly. Empty messages in the list produce an empty string. Guard with a check:

```python
combined = " ".join(m["content"] for m in messages if m.get("content"))
```

### Provider is not selected despite `LLM_PROVIDER=custom`

The factory caches provider instances in `_provider_cache`. If the application was started before you set the env variable, restart the server. In tests, clear the cache between test runs:

```python
from app.ai_agent.providers import factory
factory._provider_cache.clear()
```
