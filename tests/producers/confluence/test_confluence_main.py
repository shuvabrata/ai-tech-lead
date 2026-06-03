from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
import requests

from connectors.producers.confluence.confluence_config import load_config_from_server
from connectors.producers.confluence.main import (
    build_content_signal,
    build_person_signal,
    build_space_signal,
    process_account,
)


pytestmark = pytest.mark.unit


def test_load_config_from_server_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SERVER", "http://mock-server:8000")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "id": 7,
            "url": "https://test.atlassian.net",
            "email": "test@example.com",
            "api_token": "token123",
            "include_spaces": ["ENG"],
            "exclude_spaces": ["HR"],
            "enabled": True,
        }
    ]

    with patch(
        "connectors.producers.confluence.confluence_config.requests.get",
        return_value=mock_response,
    ) as mock_get:
        config = load_config_from_server()

    assert config == {
        "account": [
            {
                "id": 7,
                "enabled": True,
                "url": "https://test.atlassian.net",
                "email": "test@example.com",
                "api_token": "token123",
                "include_spaces": ["ENG"],
                "exclude_spaces": ["HR"],
            }
        ]
    }
    mock_get.assert_called_once_with(
        "http://mock-server:8000/api/v1/connectors/confluence/configs",
        params={"include_secrets": "true"},
        timeout=10,
    )


def test_load_config_from_server_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SERVER", "http://mock-server:8000")
    with patch("connectors.producers.confluence.confluence_config.requests.get") as mock_get:
        mock_get.side_effect = requests.exceptions.HTTPError("404 Not Found")
        with pytest.raises(requests.exceptions.HTTPError):
            load_config_from_server()


def test_build_space_signal() -> None:
    signal = build_space_signal(
        {
            "key": "eng",
            "name": "Engineering",
            "type": "global",
            "_links": {"webui": "/wiki/spaces/ENG"},
        },
        "https://example.atlassian.net",
    )
    assert signal is not None
    assert signal.source == "confluence"
    assert signal.id == "ENG"
    assert signal.attributes.entity_type == "Space"  # type: ignore[union-attr]


def test_build_person_signal() -> None:
    signal = build_person_signal(
        {"displayName": "Alice Dev", "email": "alice@example.com"},
        "acc123",
        "https://example.atlassian.net",
    )
    assert signal is not None
    assert signal.source == "confluence"
    assert signal.id == "acc123"
    assert signal.attributes.full_name == "Alice Dev"  # type: ignore[union-attr]
    assert signal.attributes.email == "alice@example.com"  # type: ignore[union-attr]


def test_build_content_signal() -> None:
    signal = build_content_signal(
        {
            "id": "2001",
            "type": "page",
            "title": "Design Notes",
            "status": "current",
            "history": {"createdDate": "2026-05-01T10:00:00Z"},
            "version": {"number": 3, "when": "2026-05-02T09:30:00Z"},
            "_links": {"webui": "/wiki/spaces/ENG/pages/2001/Design+Notes"},
        },
        "https://example.atlassian.net",
        [],
    )
    assert signal is not None
    assert signal.id == "2001"
    assert signal.attributes.entity_type == "Page"  # type: ignore[union-attr]
    assert signal.attributes.title == "Design Notes"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_process_account_publishes_space_content_and_person_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    from connectors.producers.confluence import main as confluence_main

    publisher = Mock()
    publisher.publish = AsyncMock()
    confluence = Mock()

    monkeypatch.setattr(confluence_main, "get_sync_cursor", AsyncMock(return_value=None))
    monkeypatch.setattr(confluence_main, "set_sync_cursor", AsyncMock())
    monkeypatch.setattr(
        confluence_main,
        "get_spaces",
        AsyncMock(
            return_value=[
                {
                    "key": "ENG",
                    "name": "Engineering",
                    "type": "global",
                    "_links": {"webui": "/wiki/spaces/ENG"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        confluence_main,
        "get_recent_content",
        AsyncMock(
            return_value=[
                {
                    "content": {
                        "id": "2001",
                        "type": "page",
                        "title": "Design Notes",
                        "status": "current",
                        "space": {"key": "ENG"},
                        "history": {
                            "createdDate": "2026-05-01T10:00:00Z",
                            "createdBy": {"accountId": "acc123"},
                        },
                        "version": {
                            "number": 3,
                            "when": "2026-05-02T09:30:00Z",
                            "by": {"accountId": "acc123"},
                        },
                        "_links": {"webui": "/wiki/spaces/ENG/pages/2001/Design+Notes"},
                    }
                }
            ]
        ),
    )
    monkeypatch.setattr(confluence_main, "fetch_page_body", Mock(return_value="<p>Hello</p>"))
    monkeypatch.setattr(
        confluence_main,
        "get_comments",
        AsyncMock(
            return_value=[
                {
                    "id": "c1",
                    "body": {"storage": {"value": "<p>@acc123</p>"}},
                    "history": {"createdBy": {"accountId": "acc123"}},
                    "version": {"when": "2026-05-02T11:00:00Z"},
                }
            ]
        ),
    )
    monkeypatch.setattr(
        confluence_main,
        "get_likes",
        AsyncMock(
            return_value=[
                {
                    "accountId": "acc999",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        confluence_main,
        "get_user_details_async",
        AsyncMock(
            return_value={
                "displayName": "Alice Dev",
                "email": "alice@example.com",
                "publicName": "Alice Dev",
            }
        ),
    )

    published = await process_account(
        publisher,
        confluence,
        {
            "id": 7,
            "url": "https://example.atlassian.net",
            "email": "test@example.com",
            "api_token": "token123",
            "include_spaces": [],
            "exclude_spaces": [],
            "enabled": True,
        },
    )

    assert published == 4
    assert publisher.publish.await_count == 4
    assert confluence_main.set_sync_cursor.await_count == 1

    content_signal = publisher.publish.await_args_list[1].args[0]
    relationship_types = {rel.type for rel in content_signal.relationships}
    assert "REACTED_TO" in relationship_types
