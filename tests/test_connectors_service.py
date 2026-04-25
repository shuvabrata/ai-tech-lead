from cryptography.fernet import Fernet
import pytest

from app.api.connectors.v1 import service
from app.settings import settings


pytestmark = pytest.mark.unit


@pytest.fixture
def connector_encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "CONNECTOR_ENCRYPTION_KEY", key)
    return key


def test_normalize_connector_config_masks_atlassian_token():
    config = {
        "enabled": True,
        "server_url": "https://mcp.atlassian.com/v1/mcp",
        "encrypted_token": "secret-ciphertext",
    }

    normalized = service._normalize_connector_config("atlassian_mcp", config)

    assert normalized == {
        "enabled": True,
        "server_url": "https://mcp.atlassian.com/v1/mcp",
        "token": "********",
    }


def test_normalize_connector_config_decrypts_atlassian_token(connector_encryption_key):
    encrypted_token = service.encrypt("plain-secret")
    config = {
        "enabled": True,
        "server_url": "https://mcp.atlassian.com/v1/mcp",
        "encrypted_token": encrypted_token,
    }

    normalized = service._normalize_connector_config(
        "atlassian_mcp",
        config,
        include_secrets=True,
    )

    assert normalized == {
        "enabled": True,
        "server_url": "https://mcp.atlassian.com/v1/mcp",
        "token": "plain-secret",
    }


def test_prepare_connector_config_encrypts_plaintext_token(connector_encryption_key):
    payload = {
        "enabled": True,
        "server_url": "https://mcp.atlassian.com/v1/mcp",
        "token": "plain-secret",
        "ignored_key": "ignored-value",
    }

    prepared = service._prepare_connector_config_for_storage(
        "atlassian_mcp",
        payload,
        existing_config=None,
    )

    assert prepared["enabled"] is True
    assert prepared["server_url"] == "https://mcp.atlassian.com/v1/mcp"
    assert "encrypted_token" in prepared
    assert "token" not in prepared
    assert "ignored_key" not in prepared
    assert service.decrypt(prepared["encrypted_token"]) == "plain-secret"


def test_prepare_connector_config_preserves_existing_secret_when_token_blank(connector_encryption_key):
    existing_encrypted_token = service.encrypt("existing-secret")
    existing_config = {
        "enabled": True,
        "server_url": "https://mcp.atlassian.com/v1/mcp",
        "encrypted_token": existing_encrypted_token,
    }
    payload = {
        "enabled": True,
        "server_url": "https://mcp.atlassian.com/v1/mcp",
        "token": "",
    }

    prepared = service._prepare_connector_config_for_storage(
        "atlassian_mcp",
        payload,
        existing_config=existing_config,
    )

    assert prepared["encrypted_token"] == existing_encrypted_token
    assert service.decrypt(prepared["encrypted_token"]) == "existing-secret"


def test_prepare_connector_config_returns_plain_config_for_non_atlassian():
    payload = {"any": "value"}

    prepared = service._prepare_connector_config_for_storage(
        "github_mcp",
        payload,
        existing_config=None,
    )

    assert prepared == payload


def test_validate_atlassian_mcp_config_requires_server_url_when_enabled():
    with pytest.raises(ValueError, match="server_url is required"):
        service._validate_atlassian_mcp_config(
            {"enabled": True},
            existing_config=None,
        )


def test_validate_atlassian_mcp_config_requires_token_when_enabled_without_existing_secret():
    with pytest.raises(ValueError, match="token is required"):
        service._validate_atlassian_mcp_config(
            {
                "enabled": True,
                "server_url": "https://mcp.atlassian.com/v1/mcp",
            },
            existing_config=None,
        )


def test_validate_atlassian_mcp_config_allows_missing_new_token_with_existing_secret():
    service._validate_atlassian_mcp_config(
        {
            "enabled": True,
            "server_url": "https://mcp.atlassian.com/v1/mcp",
        },
        existing_config={"encrypted_token": "existing-ciphertext"},
    )
