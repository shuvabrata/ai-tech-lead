# Migration Plan: HTTP Chat to SSE Streaming

## Problem Statement
- The current chat implementaion is HTTP based and it takes a long time for the LLM final response to be presented in the UI.
- This does not provide a good user experienece like the usual LLM chat based interface which steams words as they are generated.

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
`ai_agent.py` will expose a new generator function (e.g., `stream_chat`) instead of the blocking `do_chat`. 
- Augmentation chains (like Neo4j) will yield `thinking` chunks.
- The LLM provider (`LLMProvider`) must be updated to support a `stream_chat_completion` method that yields raw tokens.
- FastAPI will return a `StreamingResponse(media_type="text/event-stream")`.

### 3. Frontend JS Bridge
Dash cannot natively append tokens to a UI element efficiently via Python callbacks (the network overhead would crash the app). We will use a JS Bridge:
- **Dash:** Renders a placeholder container with unique HTML `id`s (e.g., `<details id="think-123">`, `<div id="msg-123">`).
- **JS Bridge (`clientside_callback`):** Intercepts the submit action, uses the browser's native `fetch()` API to make the POST request, reads the stream (`response.body.getReader()`), and mutates the DOM elements directly by ID.
- **State Sync:** When the stream ends, JS triggers a Dash state update to save the final message history in `dcc.Store` for persistence across page navigation.

## Phase-Wise Implementation Plan

### Phase 5: External/Custom Provider Developer Documentation
- After the core streaming implementation is complete and tested, draft a guide for external/custom LLM provider developers.
- The guide should describe:
  - The new required interface (`stream_chat_completion`), expected streaming behavior, and error handling.
  - How to handle disconnects, timeouts, and resource cleanup in their provider code.
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

### Phase 1: Core AI & Provider Streaming capabilities
- **Logging and Metrics for Streaming:**
  - Instrument the `stream_chat` generator and all streaming-related code paths with logging for stream start, end, disconnects, errors, and durations using the centralized logger (`app.common.logger`).
  - Log key metadata: session ID, user agent (if available), event types, and error details.
  - Add metrics counters/timers for stream starts, completions, errors, disconnects, and average duration (consider Prometheus or a simple in-memory/exported stats approach).
  - Ensure logs are structured and easily filterable for troubleshooting and monitoring.
- Add `stream_chat_completion` to `LLMProvider` base class and implement it for the active provider (e.g., OpenAI using `stream=True`).
- Update `ai_agent.py` to add a `stream_chat` generator function.
- Modify `chains.py` and `neo4j_chain.py` so they can optionaly yield orchestration thought strings.
- **Backend Error Handling for Disconnects and Timeouts:**
  - Update the `stream_chat` generator in `ai_agent.py` to catch `asyncio.CancelledError` and generator exit events, handling client disconnects gracefully.
  - Use FastAPI’s request object (if available) to check for disconnects and break the generator loop.
  - Wrap all chain and LLM calls in try/except blocks; on error, yield an SSE `{"type": "error", "content": ...}` event and ensure generator cleanup.
  - Add per-chain and per-LLM call timeouts (using `asyncio.wait_for` or provider-specific timeout options).
  - Ensure all async resources (DB sessions, HTTP clients) are closed if the stream is interrupted.
- **Automated Tests:**
  - Unit test `LLMProvider.stream_chat_completion` with a mocked streaming response to ensure it yields tokens correctly.
  - Unit test `ai_agent.stream_chat` to verify it yields correctly formatted SSE JSON dictionaries (`thinking_start`, `message_chunk`, etc.).
  - Unit test: Simulate generator exit and ensure no resource leaks or unhandled exceptions.
  - Integration test: Use FastAPI’s TestClient to simulate a client disconnect mid-stream and verify the backend logs cleanup and does not crash.
  - Integration test: Simulate a slow or stuck chain/LLM call and verify a timeout error event is sent to the client.
- **Manual Tests:**
  - Create a temporary CLI script to call `ai_agent.stream_chat` directly and print the output chunks to the console in real-time to verify the generation speed and event formats.
  - Manual test: Use `curl` or Postman, start a stream, then disconnect; check backend logs for proper cleanup.

### Phase 2: FastAPI Streaming Endpoint
- **Logging and Metrics for Streaming Endpoint:**
  - Log every `/stream` endpoint invocation, including session ID, request metadata, and outcome (success, error, disconnect, timeout).
  - Record metrics for active streams, completed streams, errors, and disconnects.
  - Expose a simple `/metrics` endpoint (optional) for Prometheus or similar scraping, or log metrics periodically for external collection.
- **Automated Tests (Logging & Metrics):**
  - Unit test: Simulate normal and error stream flows and assert logs are written for start, end, error, and disconnect events.
  - Unit test: Simulate multiple streams and verify metrics counters increment as expected.
- **Automated Tests (Logging & Metrics):**
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
- **Manual Tests:**
  - Use `curl` or Postman to send a POST request to the endpoint and visually verify that chunks arrive progressively over the network, not all at once.

### Phase 3: Dash UI Setup (Placeholders)
- Update `chat.py` UI rendering. When a user asks a question, immediately inject the message structure:
  - A `<details><summary>Analyzing Context...</summary>...</details>` element for thoughts.
  - A markdown container for the final message.
- Assign unique IDs to these elements based on the message ID.
- **Automated Tests:**
  - Unit test the Dash callback (`queue_message`) to ensure it returns the expected updated HTML structure and generates deterministic, unique IDs.
- **Manual Tests:**
  - Submit a chat message via the UI.
  - Inspect the browser DOM using DevTools to confirm the placeholder elements (`<details>` and `<div>`) are injected with the correct IDs immediately, before any backend response arrives.

### Phase 4: The JS Bridge (Clientside Callback)
- **Accessibility and Robustness for JS Bridge:**
  - Ensure all DOM updates for streamed content use ARIA live regions (e.g., `aria-live="polite"` or `aria-live="assertive"`) so screen readers announce updates.
  - Add appropriate ARIA roles and labels to streamed message containers and ensure keyboard navigation is preserved.
  - Test and fix any focus issues when new content is streamed (e.g., do not steal focus from input fields).
  - Handle all error events gracefully: display user-friendly error messages, and ensure the UI remains usable after a stream error or disconnect.
  - Add a progress indicator or spinner for long "thinking" phases, and ensure it is accessible (e.g., with `role="status"`).
  - Document accessibility features and known limitations in the user guide.
- **Automated Tests (Accessibility & Robustness):**
  - Unit test: Simulate streaming updates and verify ARIA live regions are updated as expected.
  - E2E test: Use accessibility testing tools (e.g., axe-core, pa11y) to check for violations during and after streaming.
  - E2E test: Simulate keyboard navigation and screen reader usage during streaming.
  - E2E test: Simulate stream errors and verify the UI recovers and remains accessible.
- Implement a Dash `clientside_callback` in `chat.py` (or a separate JS file in `/assets`).
- Use `fetch` to POST to the new streaming endpoint.
- Parse the SSE chunks, append `thinking_chunk`s to the `<details>` block, and `message_chunk`s to the main message block.
- Upon completion, fire an event back to a Dash Python callback to solidify the session history in the backend and `session-store`.
- **Automated Tests:**
  - End-to-End (E2E) test (e.g., using `dash.testing`) to send a message, wait for the stream to complete, and assert the final text exists in the DOM.
- **Manual Tests:**
  - **Happy Path:** Conduct an end-to-end chat in the browser. Verify the "Analyzing Context..." section streams internal thoughts and the main section streams the final response smoothly.
  - **State Persistence:** Refresh the browser page after a streamed response completes to verify the history was properly saved to the backend/`dcc.Store` and reloads without losing data.
  - **Error Handling:** Simulate a network drop or a backend crash mid-stream and ensure the JS bridge gracefully handles it and displays a user-friendly error message.