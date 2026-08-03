import pytest

from app.api.connectors.v1 import service


@pytest.mark.unit
def test_derives_configured_for_config_table_connectors_when_rows_exist():
    assert service._derive_connector_status("github", None, [object()]) == "configured"


@pytest.mark.unit
def test_derives_not_configured_for_config_table_connectors_without_rows():
    assert service._derive_connector_status("github", None, []) == "not_configured"


@pytest.mark.unit
def test_derives_configured_for_mcp_connectors_when_connector_config_exists():
    assert service._derive_connector_status("atlassian_mcp", {"server_url": "https://mcp.example"}, []) == "configured"


@pytest.mark.unit
def test_derives_not_configured_for_mcp_connectors_without_connector_config():
    assert service._derive_connector_status("atlassian_mcp", {}, []) == "not_configured"
