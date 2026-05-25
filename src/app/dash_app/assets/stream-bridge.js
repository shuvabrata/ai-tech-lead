/*
 * stream-bridge.js
 *
 * Dash clientside functions for the SSE chat stream bridge.
 *
 * Namespace: window.dash_clientside.stream
 *
 * Functions:
 *   startStream(pendingData)  — called first; immediately signals streaming is
 *                               active by returning true for the streaming-active
 *                               store. This runs synchronously so that any Python
 *                               callback guarded by streaming-active sees it as
 *                               true before it fires.
 *
     *   runStream(pendingData, sessionData, timeConfig) — returns a Promise that:
 *     1. Opens a fetch() POST to /api/v1/chats/{session_id}/stream
 *     2. Reads the SSE stream chunk-by-chunk, updating the DOM in real time:
 *          think-body-{client_id}  → thinking/progress text
 *          msg-{client_id}         → streamed response text
 *     3. On message_end: resolves with updated session-store data so Dash
 *        re-renders the styled assistant message via render_from_session.
 *     4. On error event or network failure: shows an inline error in
 *        msg-{client_id} and resolves with an error entry in session-store.
 *     5. Always sets streaming-active back to false on resolve so that the
 *        Python render_from_session callback fires.
 */

window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.stream = {

    /**
     * Synchronously set streaming-active = true as soon as pending-send fires.
     * Guards the render_from_session callback from re-rendering chat-messages
     * while the SSE stream is in progress.
     */
    startStream: function (pendingData) {
        if (!pendingData || !pendingData.session_id) {
            return window.dash_clientside.no_update;
        }
        return true;
    },

    /**
     * Main SSE stream bridge.  Returns a Promise that consumes the SSE
     * response and resolves with the updated Dash store values.
     */
    runStream: function (pendingData, sessionData, timeConfig) {
        if (!pendingData || !pendingData.session_id) {
            return window.dash_clientside.no_update;
        }

        var sessionId = pendingData.session_id;
        var message   = pendingData.message;
        var clientId  = pendingData.client_id;

        return new Promise(function (resolve) {
            var fullMessage = '';
            var fullMetadata = null;
            var resolved    = false;

            /* ── DOM helpers ──────────────────────────────────────────── */

            function updateThinkBody(text) {
                var el = document.getElementById('think-body-' + clientId);
                if (el) { el.textContent = text; }
            }

            function updateMsgContent(text) {
                var el = document.getElementById('msg-' + clientId);
                if (el) { el.textContent = text; }
            }

            function showError(errorText) {
                var el = document.getElementById('msg-' + clientId);
                if (el) {
                    el.innerHTML =
                        '<span style="color:#c0392b;">\u26a0 ' +
                        (errorText || 'An error occurred.') +
                        '</span>';
                }
            }

            function formatTimestamp() {
                var timezone = (timeConfig && timeConfig.timezone) ? timeConfig.timezone : 'UTC';
                try {
                    return new Intl.DateTimeFormat('en-US', {
                        timeZone: timezone,
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: true
                    }).format(new Date());
                } catch (err) {
                    return new Intl.DateTimeFormat('en-US', {
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: true
                    }).format(new Date());
                }
            }

            /* ── Session-store builder ────────────────────────────────── */

            function buildUpdatedSession(content, isError) {
                var messages = (sessionData && sessionData.messages)
                    ? JSON.parse(JSON.stringify(sessionData.messages))
                    : [];

                // Remove the assistant_thinking placeholder for this client_id
                var thinkIdx = messages.findIndex(function (m) {
                    return m.role === 'assistant_thinking' && m.client_id === clientId;
                });
                if (thinkIdx >= 0) { messages.splice(thinkIdx, 1); }

                // Clear the "pending" status from the matching user message
                var userMsgIdx = messages.findIndex(function (m) {
                    return m.role === 'user' && m.client_id === clientId;
                });
                if (userMsgIdx >= 0) {
                    messages[userMsgIdx] = Object.assign({}, messages[userMsgIdx]);
                    delete messages[userMsgIdx].status;
                }

                var timestamp = formatTimestamp();

                var entry = {
                    role: isError ? 'error' : 'assistant',
                    content: content,
                    timestamp: timestamp
                };
                if (!isError && fullMetadata) {
                    entry.meta = fullMetadata;
                }
                messages.push(entry);

                return Object.assign({}, sessionData, { messages: messages });
            }

            /* ── Single-resolve guard ─────────────────────────────────── */

            function safeResolve(value) {
                if (!resolved) {
                    resolved = true;
                    resolve(value);
                }
            }

            function resolveWith(content, isError) {
                safeResolve([
                    buildUpdatedSession(content, isError),  // session-store
                    null,                                   // pending-send (clear)
                    { sending: false },                     // sending-store
                    new Date().toISOString(),               // scroll-trigger
                    false                                   // streaming-active
                ]);
            }

            /* ── SSE line parser ──────────────────────────────────────── */

            var buffer = '';

            function processText(text) {
                buffer += text;
                var lines = buffer.split('\n');
                buffer = lines.pop(); // keep incomplete trailing line

                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (!line.startsWith('data: ')) { continue; }

                    var event;
                    try {
                        event = JSON.parse(line.slice(6));
                    } catch (e) {
                        continue;
                    }

                    switch (event.type) {
                        case 'thinking_chunk':
                            updateThinkBody(event.content || 'Assistant is thinking\u2026');
                            break;
                        case 'message_start':
                            updateThinkBody('Streaming response\u2026');
                            break;
                        case 'message_chunk':
                            fullMessage += (event.content || '');
                            updateMsgContent(fullMessage);
                            break;
                        case 'metadata':
                            fullMetadata = event.content || null;
                            break;
                        case 'message_end':
                            resolveWith(fullMessage, false);
                            break;
                        case 'error':
                            showError(event.content);
                            resolveWith(event.content || 'An error occurred.', true);
                            break;
                        default:
                            break;
                    }
                }
            }

            /* ── Recursive reader ─────────────────────────────────────── */

            function read(reader, decoder) {
                return reader.read().then(function (result) {
                    if (result.done) {
                        // Stream ended without a message_end (e.g. server crash)
                        if (!resolved) {
                            if (fullMessage) {
                                resolveWith(fullMessage, false);
                            } else {
                                var msg = 'Connection closed unexpectedly.';
                                showError(msg);
                                resolveWith(msg, true);
                            }
                        }
                        return;
                    }
                    processText(decoder.decode(result.value, { stream: true }));
                    return read(reader, decoder);
                });
            }

            /* ── Fetch ────────────────────────────────────────────────── */

            fetch('/api/v1/chats/' + sessionId + '/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            }).then(function (response) {
                if (!response.ok) {
                    return response.text().then(function (errText) {
                        throw new Error('HTTP ' + response.status + ': ' + errText);
                    });
                }
                var reader  = response.body.getReader();
                var decoder = new TextDecoder();
                return read(reader, decoder);
            }).catch(function (err) {
                var errMsg = (err && err.message) ? err.message : 'Network error.';
                showError(errMsg);
                resolveWith(errMsg, true);
            });
        });
    }
};
