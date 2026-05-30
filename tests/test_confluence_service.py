import pytest

from app.api.connectors.v1.service import _validate_confluence_item_payload


def test_confluence_validation_missing_url():
    data = {"api_token": "secret123"}
    with pytest.raises(ValueError, match="Confluence url is required"):
        _validate_confluence_item_payload(data, item_id=None)


def test_confluence_validation_empty_url():
    data = {"url": "   ", "api_token": "secret123"}
    with pytest.raises(ValueError, match="Confluence url is required"):
        _validate_confluence_item_payload(data, item_id=None)


def test_confluence_validation_missing_token_on_create():
    data = {"url": "https://test.atlassian.net"}
    with pytest.raises(ValueError, match="Confluence api_token is required"):
        _validate_confluence_item_payload(data, item_id=None)  # item_id=None means new creation


def test_confluence_validation_empty_token_on_update():
    data = {"url": "https://test.atlassian.net", "api_token": "   "}
    with pytest.raises(ValueError, match="Confluence api_token cannot be empty"):
        _validate_confluence_item_payload(data, item_id=1)


def test_confluence_validation_success():
    # 1. New creation: Token is provided
    _validate_confluence_item_payload({"url": "https://test.atlassian.net", "api_token": "sec"}, item_id=None)
    # 2. Update existing: Token is naturally optional if they don't want to overwrite it
    _validate_confluence_item_payload({"url": "https://test.atlassian.net"}, item_id=1)