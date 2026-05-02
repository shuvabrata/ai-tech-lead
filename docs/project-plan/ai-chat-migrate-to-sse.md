# Migration Plan: HTTP Chat to SSE Streaming

## Problem Statement
- The current chat implementation is HTTP based and it takes a long time for the LLM final response to be presented in the UI.
- This does not provide a good user experience like the usual LLM chat based interface which streams words as they are generated.

## Requirements
- **Note:** This workspace contains only the OpenAI LLM provider implementation. Other LLM providers (custom, external) are developed and maintained outside this repository. After implementing streaming, documentation must be provided for external provider authors to update their code for compatibility.
- Replace the current HTTP based chat request response to an SSE based streaming request response for the chat interface.
- If Dash cannot consume SSE natively (without overwhelming callbacks), a JS bridge must be used.
- For the chat interface users should see two type of response. 
1. A grayed out collapsible response area which streams internal transactional messages (orchestration in `ai_agent.py`). Gives transparency and a "thinking" impression.
2. A final response section which streams the actual answer.

## Architecture Design

### 1. Protocol: Server-Sent Events (SSE) via JSON
We will use standard SSE where the `data:` payload is a JSON object defining the stream phase.
Event schema:
- `{"type": "thinking_start"}`
- `{"type": "thinking_chunk", "content": "..."}`
- `{"type": "thinking_end"}`
- `{"type": "message_start"}`
- `{"type": "message_chunk", "content": "..."}`
- `{"type": "message_end"}`
- `{"type": "error", "content": "..."}`

### 2. Backend Stream Generator
`ai_agent.py` will expose a new **async** generator function (`stream_chat`) alongside the existing blocking `do_chat` (preserved for backward compatibility).
- Augmentation chains (`neo4j_chain.py`, `mcp_chain.py`, `chains.py`) will be updated to optionally yield `thinking` chunks during their processing (see Section 5).
- The LLM provider (`LLMProvider`) must be updated to support a `stream_chat_completion` method that yields raw tokens.
- `stream_chat_completion` is an **optional** method on `LLMProvider` — it raises `NotImplementedError` by default, consistent with the existing `chat_completion_with_tools` precedent. External/custom providers do not break until they choose to implement streaming.
- `stream_chat` must assemble the complete final response text and append it to `_chat_sessions` (in-memory session store) when the stream ends, so session history and token counting remain correct for subsequent turns.
- FastAPI will return a `StreamingResponse(media_type="text/event-stream")`.

### 3. Frontend JS Bridge
Dash cannot natively append tokens to a UI element efficiently via Python callbacks (the network overhead would crash the app). We will use a JS Bridge:
- **Dash:** Renders a placeholder container with unique HTML `id`s (e.g., `<details id="think-123">`, `<div id="msg-123">`).
- **JS Bridge (`clientside_callback`):** Intercepts the submit action, uses the browser's native `fetch()` API to make the POST request to `/api/v1/chats/{session_id}/stream`. Because the Dash app is WSGI-mounted at `/app` on a FastAPI (ASGI) server, the JS bridge must construct the full URL using the `API_BASE_URL` (already used by existing Dash callbacks as `http://localhost:8000` by default) — relative paths from the Dash context cannot reach FastAPI routes.
- Reads the stream (`response.body.getReader()`), and mutates the DOM elements directly by ID.
- **State Sync:** When the stream ends, JS triggers a Dash state update to save the final message history in `dcc.Store` for persistence across page navigation.

### 4. Async Strategy (Additive — Do Not Convert Existing Functions)
All existing chat functions (`do_chat`, `augment_message`, `augment_message_with_neo4j`, `augment_message_with_mcp`) are **synchronous and must remain so**. Converting them would break the CLI (`start_chat`) and risk blocking FastAPI's event loop if `async def` service/router handlers called blocking sync code.

The correct approach is **additive**: new async streaming variants are added alongside the existing synchronous functions. Nothing in the existing request path changes:
- `stream_chat` is a **new** `async def` generator in `ai_agent.py`.
- `augment_message_stream` is a **new** async generator in `chains.py` (alongside the unchanged `augment_message`).
- Async streaming variants of the neo4j and mcp chain augmentors are added as new functions.
- The **new** `/stream` router endpoint and its service function are `async def`.
- The **existing** `/{session_id}/messages` endpoint and service functions stay as synchronous `def` — FastAPI already runs them safely in a thread pool.

The Dash UI calls the HTTP API (not Python functions directly), so Dash callbacks are unaffected.

### 5. Chain Streaming Generator Contract (Core Design Decision)
The key design challenge: `augment_message` currently returns a single string, but streaming requires yielding `thinking` chunks **and** still producing a final augmented message string for the LLM. The agreed contract is:

`augment_message` and its sub-chain functions become async generators that yield SSE-compatible dicts. A sentinel event type `augmented_message` carries the final context-enriched string:

```python
async def augment_message_stream(user_message, provider) -> AsyncIterator[dict]:
    yield {"type": "thinking_chunk", "content": "Checking graph database..."}
    # ... do Neo4j / MCP work ...
    yield {"type": "thinking_end"}
    yield {"type": "augmented_message", "content": final_augmented_string}
```

`stream_chat` in `ai_agent.py` consumes this generator: it forwards all `thinking_*` events to the SSE stream, and captures the `augmented_message` event internally to pass to the LLM. LLM token chunks are then yielded as `message_chunk` events. The original synchronous `augment_message` is preserved unchanged for use by `do_chat`.

**Event ownership:** `stream_chat` (not chain generators) is responsible for emitting the initial `{"type": "thinking_start"}` event before calling `augment_message_stream`, and `{"type": "message_start"}` before yielding the first LLM token. Chain generators must not emit `thinking_start` or `message_start` — they only yield `thinking_chunk`, `thinking_end`, and `augmented_message`.

## Phase-Wise Implementation Plan

### Phase 1: Core AI & Provider Streaming capabilities ✅ COMPLETED
- **Logging and Metrics for Streaming:**
  - Instrument the `stream_chat` generator and all streaming-related code paths with logging for stream start, end, disconnects, errors, and durations using the centralized logger (`app.common.logger`).
  - Log key metadata: session ID, user agent (if available), event types, and error details.
  - Add metrics counters/timers for stream starts, completions, errors, disconnects, and average duration (consider Prometheus or a simple in-memory/exported stats approach).
  - Ensure logs are structured and easily filterable for troubleshooting and monitoring.
- Add new async streaming variants of chain augmentors (`augment_message_stream` in `chains.py`, and streaming variants in `neo4j_chain.py` and `mcp_chain.py`) following the async generator contract described in Architecture Section 5. Existing synchronous `augment_message`, `augment_message_with_neo4j`, and `augment_message_with_mcp` are **not modified** (see Architecture Section 4).
- Add `stream_chat_completion` as an optional method on `LLMProvider` base class (raises `NotImplementedError` by default, consistent with `chat_completion_with_tools`); implement it for `OpenAIProvider` using `stream=True`.
- Add `stream_chat` as a **new** async generator in `ai_agent.py` (alongside the unchanged `do_chat`). At stream end, `stream_chat` must append the assembled final response to `_chat_sessions` so session history and token counting remain intact for subsequent turns. **Important:** replicate `do_chat`'s token pruning logic (remove oldest 3 messages after the system prompt when `total_tokens > max_tokens`) before sending to the LLM — streaming sessions are subject to the same token limits.
- **Backend Error Handling for Disconnects and Timeouts:**
  - Update the `stream_chat` generator in `ai_agent.py` to catch `asyncio.CancelledError` and generator exit events, handling client disconnects gracefully.
  - Use FastAPI’s request object (if available) to check for disconnects and break the generator loop.
  - Wrap all chain and LLM calls in try/except blocks; on error, yield an SSE `{"type": "error", "content": ...}` event and ensure generator cleanup.
  - Add per-chain and per-LLM call timeouts (using `asyncio.wait_for` or provider-specific timeout options).
  - Ensure all async resources (DB sessions, HTTP clients) are closed if the stream is interrupted.
- **Automated Tests:**
  - Unit test `OpenAIProvider.stream_chat_completion` with a mocked streaming response to ensure it yields tokens correctly. (`LLMProvider.stream_chat_completion` only raises `NotImplementedError` by design; the behaviour under test lives in `OpenAIProvider`.)
  - Unit test `ai_agent.stream_chat` to verify it yields correctly formatted SSE JSON dictionaries (`thinking_start`, `message_chunk`, etc.).
  - Unit test: Simulate generator exit and ensure no resource leaks or unhandled exceptions.
  - Integration test: Simulate a client disconnect mid-stream using `httpx.AsyncClient` against the ASGI app directly (e.g., via `pytest-anyio`). `TestClient` is synchronous and buffers the full response before returning — it cannot abort mid-stream and must not be used for disconnect tests.
  - Integration test: Simulate a slow or stuck chain/LLM call and verify a timeout error event is sent to the client.
- **Manual Tests:** ✅ COMPLETED
  - **CLI script test** (`scripts/test_stream_chat.py`): Called `ai_agent.stream_chat` directly against a live system (OpenAI `gpt-4o` + Neo4j + MCP). Verified progressive token delivery, correct event sequence (`thinking_start` → `thinking_chunk` × 2 → `thinking_end` × 2 → `message_start` → `message_chunk` × N → `message_end`), and real-time console output.
  - **curl disconnect test** (via `scripts/temp_stream_server.py`, a temporary minimal FastAPI server on port 8001):
    - Full stream: `curl -N -X POST http://localhost:8001/stream/{session_id}` — confirmed all event types arrive progressively, stream terminates with `message_end`.
    - Mid-stream disconnect: piped through `head -5` to kill the connection after 3 events (`thinking_start`, `thinking_chunk`, `thinking_end`). Server logged the disconnect and `disconnects` metric incremented to `1`.
    - Metrics endpoint (`GET /metrics`) confirmed after both tests: `{"starts": 2, "completions": 1, "errors": 0, "disconnects": 1, "total_duration_seconds": 12.15}`.
  - Temp server script (`scripts/temp_stream_server.py`) is retained for reference but is not part of the production codebase.

### Phase 2: FastAPI Streaming Endpoint ✅ COMPLETED
- **Logging and Metrics for Streaming Endpoint:**
  - Log every `/stream` endpoint invocation, including session ID, request metadata, and outcome (success, error, disconnect, timeout).
  - Record metrics for active streams, completed streams, errors, and disconnects.
  - Expose a simple `/metrics` endpoint (optional) for Prometheus or similar scraping, or log metrics periodically for external collection.
- **Automated Unit Tests (Logging & Metrics):**
  - Unit test: Simulate normal and error stream flows and assert logs are written for start, end, error, and disconnect events.
  - Unit test: Simulate multiple streams and verify metrics counters increment as expected.
- **Automated Integration Tests (Logging & Metrics):**
  - Integration test: Start and complete a stream, then check logs/metrics for correct entries.
  - Integration test: Simulate disconnects and errors, verify logs/metrics reflect the events.
  - (Optional) Integration test: Scrape `/metrics` endpoint and verify values.
- Create a new route in FastAPI: `POST /api/v1/chats/{session_id}/stream`.
- Wrap the `ai_agent.stream_chat` generator in an async format suitable for `fastapi.responses.StreamingResponse`.
- **Backend Error Handling for Streaming Endpoint:**
  - In the `/stream` endpoint, ensure the StreamingResponse is wrapped in a try/except/finally block.
  - Log disconnects and timeouts using the centralized logger.
  - Return a final SSE error event if the stream is interrupted by a backend error.
- **Automated Tests:**
  - Integration test using FastAPI's `TestClient` to POST to the `/stream` endpoint and assert the response `Content-Type` is `text/event-stream`.
  - Integration test to consume the stream programmatically and validate the sequence of JSON event payloads.
  - Integration test: Simulate network drop during streaming and verify the backend logs the disconnect and does not leave open resources.
  - Integration test: Simulate backend timeout and verify the client receives an SSE error event.
- **Manual Tests:** ✅ COMPLETED
  - Full stream: `curl -N -X POST http://localhost:8000/api/v1/chats/{session_id}/stream` — confirmed `text/event-stream` content-type, progressive SSE delivery, correct event sequence through to `message_end`.
  - Disconnect mid-stream: piped through `head -5`, disconnect metric incremented to `1` as confirmed via `GET /api/v1/chats/metrics/stream`.
  - Unknown session: `POST /api/v1/chats/nonexistent-session/stream` returned JSON `404` (not a broken SSE stream).
  - Metrics endpoint: `GET /api/v1/chats/metrics/stream` returned all expected keys (`starts`, `completions`, `errors`, `disconnects`, `total_duration_seconds`).

### Phase 3: Dash UI Setup (Placeholders) ✅ COMPLETED
- **Design decisions (confirmed):**
  - Keep the existing `assistant_thinking` visual style unchanged (diamond icon, italic text, left border). Do not wrap in `<details>` — just add IDs to the existing elements.
  - Summary/placeholder wording stays **"Assistant is thinking…"** (not "Analyzing Context...").
  - The companion `<div id="msg-{client_id}">` starts as an empty div with no placeholder text — JS fills it when chunks arrive.
  - `dcc.Loading` spinner hiding is deferred to Phase 4 (when the JS bridge takes over from `send_message`).
- `chat.py` already injects an `assistant_thinking` role message into `messages` inside the `queue_message` callback, which renders a placeholder while waiting for the backend response. Phase 3 must **update this existing pattern** rather than create new elements from scratch:
  - Add `id=f"think-{client_id}"` to the outer wrapper `html.Div` of the `assistant_thinking` block.
  - Add `id=f"think-body-{client_id}"` to the inner text `html.Div` (the one currently showing "Assistant is thinking…") — this is where JS will append thinking chunks.
  - Append a companion `html.Div(id=f"msg-{client_id}")` immediately after the thinking block — this is where JS will write the final streamed response.
- **Note:** `render_messages` returns Dash Python component objects. Extract `client_id = msg.get("client_id", "")` inside the render loop to make it available for the `assistant_thinking` branch.
- The `client_id` (already generated as a timestamp-based unique value in `queue_message`) serves as the unique ID for all three containers — no new ID generation logic is needed.
- These IDs must be stable from the moment the placeholder is injected, as the JS bridge (Phase 4) targets them by ID for direct DOM mutation.
- **Automated Tests:**
  - Unit test the `render_messages` function to ensure the `assistant_thinking` role produces HTML with the expected `id` attributes (`think-{client_id}` and `msg-{client_id}`).
  - Unit test the `queue_message` callback to confirm the `client_id` in the injected `assistant_thinking` message is unique per submission (two calls with the same `n_clicks` at different times must produce different IDs).
- **Manual Tests:** ✅ COMPLETED
  - Submitted a chat message via the UI while the app ran in Docker.
  - Inspected the browser DOM using DevTools Elements panel while "Assistant is thinking…" was visible.
  - Confirmed three elements with the correct `client_id` suffix were present immediately upon placeholder injection:
    - `id="think-{client_id}"` — outer wrapper div
    - `id="think-body-{client_id}"` — italic "Assistant is thinking…" text div
    - `id="msg-{client_id}"` — empty companion div (no children) ready for Phase 4 JS to fill
  - Confirmed all three IDs share the same `client_id` value (timestamp + click count).
  - Confirmed non-thinking roles (`user`, `assistant`, `error`) produce no `think-*` or `msg-*` IDs.

### Phase 4: The JS Bridge (Clientside Callback) ✅ COMPLETED
- **Before implementing the JS bridge, disable or remove the existing `send_message` Python callback.** Currently `send_message` fires whenever `pending-send` store changes — the same trigger the JS bridge will use. Without removal, both the Python callback and the JS bridge will fire simultaneously: the Python callback hits the old `/messages` endpoint while the JS bridge hits `/stream`, causing a race condition and double responses. The `send_message` callback must be removed (or its trigger changed to a separate JS-only-controlled store) before Phase 4 work begins.
- Implement a Dash `clientside_callback` in `chat.py` (or a separate JS file in `/assets`).
- Use `fetch` to POST to the new streaming endpoint.
- Parse the SSE chunks, update `thinking_chunk`s in the thinking placeholder, and accumulate `message_chunk`s in the message div.
- Upon stream completion, JS directly writes the final session data to `session-store` (Option B) so Dash re-renders styled messages via a guarded Python callback.
- **Guard against mid-stream Dash re-renders:** The JS bridge mutates DOM elements by ID directly. A `streaming-active` store flag is set by a synchronous clientside callback at stream start and cleared at stream end. A Python `render_from_session` callback is triggered by `streaming-active` changes and returns `no_update` while streaming is active.
- **Automated Tests:**
  - Layout test: verify `streaming-active` store is present with default `False`.
  - Unit tests for `render_from_session`: no_update while streaming, renders on stream end, no_update with None session.
  - Asset tests: verify `stream-bridge.js` exists and declares required functions.
- **Manual Tests:**
  - **Happy Path:** Conduct an end-to-end chat in the browser. Verify the thinking section updates during context gathering, the response streams smoothly, and the styled assistant message appears on completion.
  - **State Persistence:** Refresh the browser page after a streamed response completes to verify the history was properly saved to `dcc.Store` and reloads without losing data.
  - **Error Handling:** Simulate a network drop or a backend crash mid-stream and ensure the JS bridge gracefully handles it and displays a user-friendly error message.

**Phase 4 Completion Evidence (automated):**
- 12 Phase 4 tests: all passed (`tests/test_chat_phase4.py`)
  - Layout: `streaming-active` store present with `data=False`
  - `render_from_session` returns `no_update` while streaming=True, re-renders when False
  - `stream-bridge.js` asset exists, declares `dash_clientside.stream`, `startStream`, `runStream`
- All prior Phase 1–3 stream/chat tests: still passing (49/49 total)
- `test_chat_flow_phase5_integration.py` migrated from `/messages` to `/stream` endpoint: all 8 tests passed

**Phase 4 implementation summary:**
- Removed `POST /{session_id}/messages` endpoint, `send_chat_message` service, `MessageCreate`/`MessageResponse` models.
- Removed `send_message` Python callback from `chat.py`.
- Added `dcc.Store(id="streaming-active")` to layout.
- Created `src/app/dash_app/assets/stream-bridge.js` with `startStream` (sync guard) and `runStream` (Promise-based SSE consumer).
- Added two `clientside_callback`s in `chat.py` wired to `stream-bridge.js`.
- Added `render_from_session` Python callback: re-renders `chat-messages` from `session-store` when `streaming-active` transitions to False.

### Phase 5: External/Custom Provider Developer Documentation
- After the core streaming implementation is complete and tested, draft a guide for external/custom LLM provider developers.
- The guide should describe:
  - The `stream_chat_completion` interface: it is **optional** on `LLMProvider` (raises `NotImplementedError` by default, consistent with `chat_completion_with_tools`). Provider authors must implement it to enable streaming; without it, the `/stream` endpoint will return an error.
  - Expected streaming behavior, error handling, and how to handle disconnects, timeouts, and resource cleanup in their provider code.
  - Example code and test cases for compliance.
- **Manual Task:**
  - Review the final implementation and update the documentation to reflect any changes or lessons learned during integration.
  - Distribute the documentation to all known external provider maintainers.
- **Documentation and Migration Notes:**
  - Update OpenAPI/Swagger documentation to include the new `/api/v1/chats/{session_id}/stream` endpoint, with event schema and example payloads.
  - Add a migration section to USER_GUIDE.md and DEVELOPER_QUICK_START.md describing how to switch from the old HTTP chat endpoint to the new SSE streaming endpoint, including code and UI changes.
  - Document the event types, error handling, and expected client behaviors for both backend and frontend developers.
  - Add a troubleshooting section for common streaming issues (disconnects, timeouts, browser compatibility).
  - Ensure all new/changed APIs are reflected in the API reference docs.
- **Automated Tests (Docs & Migration):**
  - Unit test: Validate OpenAPI schema includes the streaming endpoint and correct event types.
  - Manual test: Follow migration steps in USER_GUIDE.md and verify a developer can upgrade an integration from HTTP to SSE using only the docs.
  - Manual test: Review documentation for clarity, completeness, and accuracy.