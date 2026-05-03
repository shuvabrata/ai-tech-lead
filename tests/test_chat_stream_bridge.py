"""Automated tests for the JS stream bridge, streaming-active guard, and render_from_session.

Tests cover:
- streaming-active store is present in the Dash layout
- render_from_session returns no_update while streaming is active
- render_from_session returns no_update when session data is absent
- render_from_session re-renders chat-messages when streaming finishes
- stream-bridge.js asset exists and declares required namespace/functions
"""

from __future__ import annotations

import os

import pytest
from dash import no_update

from app.dash_app.pages.chat import get_layout, render_from_session
from app.settings import settings

pytestmark = pytest.mark.unit


# ── helpers ───────────────────────────────────────────────────────────────────


def _find_by_id(component, target_id: str):
    """Recursively search a Dash component tree for a component with the given id."""
    if hasattr(component, "id") and component.id == target_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, list):
        children = [children]
    for child in children:
        result = _find_by_id(child, target_id)
        if result is not None:
            return result
    return None


_ASSETS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "src", "app", "dash_app", "assets"
)
_STREAM_BRIDGE = os.path.join(_ASSETS_DIR, "stream-bridge.js")


# ── layout tests ──────────────────────────────────────────────────────────────


def test_streaming_active_store_in_layout():
    """streaming-active dcc.Store is present in the chat page layout."""
    layout = get_layout()
    store = _find_by_id(layout, "streaming-active")
    assert store is not None, "streaming-active store not found in layout"


def test_streaming_active_store_defaults_to_false():
    """streaming-active store has data=False as its default value."""
    layout = get_layout()
    store = _find_by_id(layout, "streaming-active")
    assert store is not None
    assert store.data is False


def test_chat_time_config_store_exposes_app_timezone():
    """The browser bridge receives the same configured timezone as the Python UI."""
    layout = get_layout()
    store = _find_by_id(layout, "chat-time-config")
    assert store is not None
    assert store.data == {"timezone": settings.TIMEZONE}


# ── render_from_session callback tests ────────────────────────────────────────


def test_render_from_session_returns_no_update_while_streaming():
    """render_from_session does nothing while streaming is active."""
    result = render_from_session(True, {"session_id": "s1", "messages": []})
    assert result is no_update


def test_render_from_session_returns_no_update_with_no_session():
    """render_from_session does nothing when session_data is None."""
    result = render_from_session(False, None)
    assert result is no_update


def test_render_from_session_renders_empty_messages_when_stream_done():
    """render_from_session renders the empty-state placeholder when messages is []."""
    session_data = {"session_id": "s1", "messages": []}
    result = render_from_session(False, session_data)
    assert result is not no_update
    assert isinstance(result, list)


def test_render_from_session_renders_user_and_assistant_when_stream_done():
    """render_from_session re-renders styled messages after streaming ends."""
    session_data = {
        "session_id": "s1",
        "messages": [
            {"role": "user", "content": "Hello", "timestamp": "10:00 AM"},
            {"role": "assistant", "content": "World", "timestamp": "10:01 AM"},
        ],
    }
    result = render_from_session(False, session_data)
    assert result is not no_update
    assert isinstance(result, list)
    assert len(result) == 2


def test_render_from_session_ignores_thinking_role_gracefully():
    """assistant_thinking entries produce DOM placeholders without crashing."""
    session_data = {
        "session_id": "s1",
        "messages": [
            {"role": "user", "content": "Hi", "timestamp": "10:00 AM"},
            {
                "role": "assistant_thinking",
                "content": "",
                "timestamp": "10:00 AM",
                "client_id": "abc123",
            },
        ],
    }
    result = render_from_session(False, session_data)
    assert result is not no_update
    assert isinstance(result, list)


# ── JS asset tests ─────────────────────────────────────────────────────────────


def test_stream_bridge_js_exists():
    """stream-bridge.js is present in the Dash assets directory."""
    assert os.path.isfile(_STREAM_BRIDGE), (
        f"stream-bridge.js not found at {_STREAM_BRIDGE}"
    )


def test_stream_bridge_js_declares_dash_clientside_namespace():
    """stream-bridge.js registers functions on window.dash_clientside.stream."""
    with open(_STREAM_BRIDGE, encoding="utf-8") as fh:
        content = fh.read()
    assert "dash_clientside" in content
    assert "window.dash_clientside.stream" in content


def test_stream_bridge_js_contains_start_stream_function():
    """stream-bridge.js defines the startStream function."""
    with open(_STREAM_BRIDGE, encoding="utf-8") as fh:
        content = fh.read()
    assert "startStream" in content


def test_stream_bridge_js_contains_run_stream_function():
    """stream-bridge.js defines the runStream function."""
    with open(_STREAM_BRIDGE, encoding="utf-8") as fh:
        content = fh.read()
    assert "runStream" in content


def test_stream_bridge_js_formats_time_using_configured_timezone():
    """stream-bridge.js should format timestamps with Intl.DateTimeFormat and a timeZone option."""
    with open(_STREAM_BRIDGE, encoding="utf-8") as fh:
        content = fh.read()
    assert "Intl.DateTimeFormat" in content
    assert "timeZone" in content


def test_stream_bridge_js_handles_stream_endpoint():
    """stream-bridge.js calls the /stream endpoint."""
    with open(_STREAM_BRIDGE, encoding="utf-8") as fh:
        content = fh.read()
    assert "/stream" in content
