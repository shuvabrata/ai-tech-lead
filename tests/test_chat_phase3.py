"""Automated tests for Phase 3: Dash UI placeholder IDs.

Coverage:
- render_messages with assistant_thinking role produces think-{client_id} on outer div
- render_messages with assistant_thinking role produces think-body-{client_id} on inner text div
- render_messages appends companion msg-{client_id} div after thinking block
- queue_message generates a unique client_id per call
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find_by_id(component, target_id: str):
    """Recursively search a Dash component tree for a component with the given id."""
    if isinstance(component, list):
        for c in component:
            result = _find_by_id(c, target_id)
            if result is not None:
                return result
        return None
    if hasattr(component, "id") and component.id == target_id:
        return component
    children = getattr(component, "children", None)
    if children:
        return _find_by_id(children, target_id)
    return None


def _make_thinking_messages(client_id: str) -> list[dict]:
    return [{"role": "assistant_thinking", "content": "", "timestamp": "12:00 PM", "client_id": client_id}]


# ─────────────────────────────────────────────────────────────────────────────
# 1. think-{client_id} on the outer wrapper div
# ─────────────────────────────────────────────────────────────────────────────

class TestThinkingBlockIds:

    def test_outer_div_has_think_id(self):
        from app.dash_app.pages.chat import render_messages

        client_id = "test-client-001"
        rendered = render_messages(_make_thinking_messages(client_id))

        result = _find_by_id(rendered, f"think-{client_id}")
        assert result is not None, f"Expected element with id='think-{client_id}' not found"

    def test_inner_text_div_has_think_body_id(self):
        from app.dash_app.pages.chat import render_messages

        client_id = "test-client-002"
        rendered = render_messages(_make_thinking_messages(client_id))

        result = _find_by_id(rendered, f"think-body-{client_id}")
        assert result is not None, f"Expected element with id='think-body-{client_id}' not found"

    def test_companion_msg_div_is_present(self):
        from app.dash_app.pages.chat import render_messages

        client_id = "test-client-003"
        rendered = render_messages(_make_thinking_messages(client_id))

        result = _find_by_id(rendered, f"msg-{client_id}")
        assert result is not None, f"Expected element with id='msg-{client_id}' not found"

    def test_all_three_ids_present_for_same_client_id(self):
        from app.dash_app.pages.chat import render_messages

        client_id = "test-client-004"
        rendered = render_messages(_make_thinking_messages(client_id))

        for suffix in (f"think-{client_id}", f"think-body-{client_id}", f"msg-{client_id}"):
            assert _find_by_id(rendered, suffix) is not None, f"Missing id='{suffix}'"

    def test_ids_use_correct_client_id(self):
        """IDs must embed the exact client_id from the message dict."""
        from app.dash_app.pages.chat import render_messages

        client_id = "20260502123456789012-42"
        rendered = render_messages(_make_thinking_messages(client_id))

        think = _find_by_id(rendered, f"think-{client_id}")
        body = _find_by_id(rendered, f"think-body-{client_id}")
        msg = _find_by_id(rendered, f"msg-{client_id}")

        assert think is not None
        assert body is not None
        assert msg is not None

    def test_non_thinking_roles_not_affected(self):
        """user and assistant roles must not produce think-* or msg-* IDs."""
        from app.dash_app.pages.chat import render_messages

        messages = [
            {"role": "user", "content": "hello", "timestamp": "12:00 PM", "client_id": "u-1"},
            {"role": "assistant", "content": "hi", "timestamp": "12:01 PM", "client_id": "a-1"},
        ]
        rendered = render_messages(messages)

        assert _find_by_id(rendered, "think-u-1") is None
        assert _find_by_id(rendered, "think-a-1") is None
        assert _find_by_id(rendered, "msg-u-1") is None
        assert _find_by_id(rendered, "msg-a-1") is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. queue_message generates unique client_ids
# ─────────────────────────────────────────────────────────────────────────────

class TestQueueMessageClientIdUniqueness:

    def test_client_id_is_unique_per_call(self):
        """Two consecutive calls to queue_message must produce different client_ids."""
        from app.dash_app.pages.chat import queue_message

        session_data = {"session_id": "sess-abc", "messages": []}

        _, _, data1, pending1, _, _ = queue_message(1, "first message", dict(session_data))
        _, _, data2, pending2, _, _ = queue_message(2, "second message", {"session_id": "sess-abc", "messages": []})

        cid1 = pending1.get("client_id")
        cid2 = pending2.get("client_id")

        assert cid1 is not None
        assert cid2 is not None
        assert cid1 != cid2, f"client_ids must be unique but both were '{cid1}'"

    def test_client_id_injected_into_assistant_thinking_message(self):
        """The assistant_thinking message in session_data must carry the same client_id as pending_send."""
        from app.dash_app.pages.chat import queue_message

        _, _, session_data, pending, _, _ = queue_message(1, "hello", {"session_id": "sess-xyz", "messages": []})

        client_id = pending.get("client_id")
        thinking_msgs = [m for m in session_data["messages"] if m.get("role") == "assistant_thinking"]

        assert len(thinking_msgs) == 1
        assert thinking_msgs[0].get("client_id") == client_id
