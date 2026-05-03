from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.common.timezone import to_app_timezone
from app.dash_app.pages.chat import queue_message
from app.dash_app.pages.connectors.callbacks import render_items_list
from app.settings import Settings, settings


pytestmark = pytest.mark.unit


def _build_settings(**kwargs) -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
        _env_file=None,
        **kwargs,
    )


def test_timezone_setting_prefers_timezone_env_over_tz(monkeypatch):
    monkeypatch.setenv("TIMEZONE", "America/New_York")
    monkeypatch.setenv("TZ", "Asia/Kolkata")

    configured = _build_settings()

    assert configured.TIMEZONE == "America/New_York"


def test_timezone_setting_falls_back_to_tz_env(monkeypatch):
    monkeypatch.delenv("TIMEZONE", raising=False)
    monkeypatch.setenv("TZ", "Asia/Kolkata")

    configured = _build_settings()

    assert configured.TIMEZONE == "Asia/Kolkata"


def test_timezone_setting_defaults_to_utc(monkeypatch):
    monkeypatch.delenv("TIMEZONE", raising=False)
    monkeypatch.delenv("TZ", raising=False)

    configured = _build_settings()

    assert configured.TIMEZONE == "UTC"


def test_timezone_setting_rejects_invalid_timezone(monkeypatch):
    monkeypatch.setenv("TIMEZONE", "Mars/Olympus")
    monkeypatch.delenv("TZ", raising=False)

    with pytest.raises(ValueError, match="Invalid timezone"):
        _build_settings()


def test_to_app_timezone_uses_configured_timezone(monkeypatch):
    monkeypatch.setattr(settings, "TIMEZONE", "Asia/Kolkata")

    converted = to_app_timezone(datetime(2026, 5, 3, 0, 0, tzinfo=timezone.utc))

    assert converted.isoformat() == "2026-05-03T05:30:00+05:30"


def test_render_items_list_formats_connector_timestamp_in_app_timezone(monkeypatch):
    monkeypatch.setattr(settings, "TIMEZONE", "Asia/Kolkata")
    monkeypatch.setattr(settings, "UI_DATETIME_FORMAT", "%b %d, %Y %I:%M %p")

    rendered = render_items_list(
        {
            "status": "ok",
            "connector_type": "github",
            "items": [
                {
                    "id": 1,
                    "url": "https://github.com/org/repo",
                    "updated_at": "2026-05-03T00:00:00+00:00",
                }
            ],
        }
    )

    header_text = rendered[0].children[0].children

    assert header_text == "Repository: last configured at May 03, 2026 05:30 AM"


def test_queue_message_uses_app_timezone_for_ui_timestamps(monkeypatch):
    fixed_now = datetime(2026, 5, 3, 5, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("app.dash_app.pages.chat.now_in_app_timezone", lambda: fixed_now)

    _, _, session_data, pending, _, _ = queue_message(
        1,
        "hello",
        {"session_id": "sess-123", "messages": []},
    )

    assert pending["client_id"]
    assert session_data["messages"][0]["timestamp"] == "05:30 AM"
    assert session_data["messages"][1]["timestamp"] == "05:30 AM"
