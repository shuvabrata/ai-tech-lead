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
    with pytest.raises(ValueError, match="Server URL is required"):
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


# ============================================================================
# Phase 5: Real test_connection helpers
# ============================================================================


class TestAtlassianMCPTestConnection:
    """Unit tests for _test_atlassian_mcp_connection."""

    @pytest.mark.asyncio
    async def test_atlassian_test_connection_success(self):
        """Returns success when check_connection returns connected=True."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        mock_connector_data = {
            "connector_type": "atlassian_mcp",
            "config": {
                "enabled": True,
                "server_url": "https://mcp.atlassian.com/v1/mcp",
                "token": "Atlassian_test_token_value",
            },
        }
        mock_manager = MagicMock()
        mock_manager.check_connection.return_value = {"connected": True}

        with patch.object(service, "get_connector", new=AsyncMock(return_value=mock_connector_data)):
            with patch("app.api.connectors.v1.service.query") as mock_query:
                mock_query.update_connector_status = AsyncMock()
                with patch(
                    "app.ai_agent.mcp_integration.client_manager.AtlassianMCPClientManager",
                    return_value=mock_manager,
                ):
                    db = MagicMock()
                    result = await service._test_atlassian_mcp_connection(db, now)

        assert result["success"] is True
        assert "Atlassian" in result["message"]

    @pytest.mark.asyncio
    async def test_atlassian_test_connection_failure_persists_error(self, monkeypatch):
        """Returns failure and persists error message when check_connection fails."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        mock_connector_data = {
            "connector_type": "atlassian_mcp",
            "config": {
                "enabled": True,
                "server_url": "https://mcp.atlassian.com/v1/mcp",
                "token": "ATATT3xFfGF0_bad_token",
            },
        }
        mock_manager = MagicMock()
        mock_manager.check_connection.return_value = {
            "connected": False,
            "error": "atlassian_mcp_token_invalid_format",
        }

        with patch.object(service, "get_connector", new=AsyncMock(return_value=mock_connector_data)):
            with patch("app.api.connectors.v1.service.query") as mock_query:
                mock_query.update_connector_status = AsyncMock()
                with patch(
                    "app.ai_agent.mcp_integration.client_manager.AtlassianMCPClientManager",
                    return_value=mock_manager,
                ):
                    db = MagicMock()
                    result = await service._test_atlassian_mcp_connection(db, now)

        assert result["success"] is False
        assert "atlassian_mcp_token_invalid_format" in result["message"]

    @pytest.mark.asyncio
    async def test_atlassian_test_connection_disabled(self):
        """Returns failure with disabled error when connector is not enabled."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        mock_connector_data = {
            "connector_type": "atlassian_mcp",
            "config": {"enabled": False, "server_url": "", "token": None},
        }
        mock_manager = MagicMock()
        mock_manager.check_connection.return_value = {
            "connected": False,
            "error": "atlassian_mcp_disabled",
        }

        with patch.object(service, "get_connector", new=AsyncMock(return_value=mock_connector_data)):
            with patch("app.api.connectors.v1.service.query") as mock_query:
                mock_query.update_connector_status = AsyncMock()
                with patch(
                    "app.ai_agent.mcp_integration.client_manager.AtlassianMCPClientManager",
                    return_value=mock_manager,
                ):
                    db = MagicMock()
                    result = await service._test_atlassian_mcp_connection(db, now)

        assert result["success"] is False


class TestGithubMCPTestConnection:
    """Unit tests for _test_github_mcp_connection."""

    @pytest.mark.asyncio
    async def test_github_test_connection_success(self):
        """Returns success when check_connection returns connected=True."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        mock_manager = MagicMock()
        mock_manager.check_connection.return_value = {"connected": True}

        with patch("app.api.connectors.v1.service.query") as mock_query:
            mock_query.update_connector_status = AsyncMock()
            with patch(
                "app.ai_agent.mcp_integration.client_manager.GithubMCPClientManager",
                return_value=mock_manager,
            ):
                db = MagicMock()
                result = await service._test_github_mcp_connection(db, now)

        assert result["success"] is True
        assert "GitHub" in result["message"]

    @pytest.mark.asyncio
    async def test_github_test_connection_disabled(self, monkeypatch):
        """Returns failure when GitHub MCP is disabled in env settings."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import datetime, timezone

        monkeypatch.setattr(settings, "GITHUB_MCP_ENABLED", False)

        now = datetime.now(timezone.utc)
        mock_manager = MagicMock()
        mock_manager.check_connection.return_value = {
            "connected": False,
            "error": "github_mcp_disabled",
        }

        with patch("app.api.connectors.v1.service.query") as mock_query:
            mock_query.update_connector_status = AsyncMock()
            with patch(
                "app.ai_agent.mcp_integration.client_manager.GithubMCPClientManager",
                return_value=mock_manager,
            ):
                db = MagicMock()
                result = await service._test_github_mcp_connection(db, now)

        assert result["success"] is False
        assert "github_mcp_disabled" in result["message"]

    @pytest.mark.asyncio
    async def test_github_test_connection_failure_persists_error(self):
        """Persists error message in the DB when the check fails."""
        from unittest.mock import AsyncMock, MagicMock, call, patch
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        mock_manager = MagicMock()
        mock_manager.check_connection.return_value = {
            "connected": False,
            "error": "connection refused",
        }

        with patch("app.api.connectors.v1.service.query") as mock_query:
            mock_query.update_connector_status = AsyncMock()
            with patch(
                "app.ai_agent.mcp_integration.client_manager.GithubMCPClientManager",
                return_value=mock_manager,
            ):
                db = MagicMock()
                result = await service._test_github_mcp_connection(db, now)

        assert result["success"] is False
        # DB status should be "error" not "connected"
        mock_query.update_connector_status.assert_awaited_once()
        call_kwargs = mock_query.update_connector_status.call_args.kwargs
        assert call_kwargs.get("status") == "error"
