import uuid

import httpx
import pytest


BASE_URL = "http://localhost:8000"
CONNECTOR_TYPE = "github"
ATLASSIAN_MCP_CONNECTOR_TYPE = "atlassian_mcp"


pytestmark = [pytest.mark.integration, pytest.mark.server]


def _marker_value() -> str:
    return f"integration-{uuid.uuid4()}"


import pytest

pytestmark = pytestmark + [pytest.mark.skip(reason="Disabled: modifies connector DB state")]

@pytest.mark.asyncio
@pytest.mark.skip(reason="Disabled: modifies connector DB state")
async def test_connectors_api_endpoints():
    created_item_ids = []
    changed_config = False
    original_config = None
    initial_items = []
    marker = _marker_value()

    async with httpx.AsyncClient(base_url=BASE_URL) as ac:
        try:
            print("Step 1: GET /api/v1/connectors/")
            resp = await ac.get("/api/v1/connectors/")
            assert resp.status_code == 200
            connectors = resp.json()
            assert any(c.get("connector_type") == CONNECTOR_TYPE for c in connectors)

            print("Step 2: GET /api/v1/connectors/{connector_type}")
            resp = await ac.get(f"/api/v1/connectors/{CONNECTOR_TYPE}")
            assert resp.status_code == 200
            original_config = resp.json().get("config")

            print("Step 3: PATCH /api/v1/connectors/{connector_type} (set marker)")
            updated_config = dict(original_config) if isinstance(original_config, dict) else {}
            updated_config["__test_marker"] = marker
            resp = await ac.patch(
                f"/api/v1/connectors/{CONNECTOR_TYPE}",
                json={"config": updated_config},
            )
            assert resp.status_code == 200
            changed_config = True

            print("Step 4: GET /api/v1/connectors/{connector_type} (verify marker)")
            resp = await ac.get(f"/api/v1/connectors/{CONNECTOR_TYPE}")
            assert resp.status_code == 200
            assert resp.json().get("config", {}).get("__test_marker") == marker

            print("Step 5: GET /api/v1/connectors/{connector_type}/configs (snapshot)")
            resp = await ac.get(f"/api/v1/connectors/{CONNECTOR_TYPE}/configs")
            assert resp.status_code == 200
            initial_items = resp.json()

            print("Step 6: GET unknown connector type (expect 404)")
            resp = await ac.get("/api/v1/connectors/unknown")
            assert resp.status_code == 404

            print("Step 7: GET unknown connector configs (expect 404)")
            resp = await ac.get("/api/v1/connectors/unknown/configs")
            assert resp.status_code == 404

            print("Step 8: POST /api/v1/connectors/{connector_type}/configs without token (expect 400)")
            missing_token_payload = {
                "url": f"https://github.com/example/{marker}-missing-token",
                "branch_name_patterns": ["main"],
                "extraction_sources": ["branch"],
            }
            resp = await ac.post(
                f"/api/v1/connectors/{CONNECTOR_TYPE}/configs",
                json=missing_token_payload,
            )
            assert resp.status_code == 400

            print("Step 9: POST /api/v1/connectors/{connector_type}/configs (create)")
            create_payload = {
                "url": f"https://github.com/example/{marker}",
                "access_token": f"token-{marker}",
                "search_filters": {
                    "props.application-context": "production",
                    "props.division": "engineering",
                },
                "branch_name_patterns": ["main"],
                "extraction_sources": ["branch"],
            }
            resp = await ac.post(
                f"/api/v1/connectors/{CONNECTOR_TYPE}/configs",
                json=create_payload,
            )
            assert resp.status_code == 200
            created_item = resp.json()
            item_id = created_item.get("id")
            assert item_id is not None
            created_item_ids.append(item_id)

            print("Step 10: GET /api/v1/connectors/{connector_type}/configs (verify mask)")
            resp = await ac.get(f"/api/v1/connectors/{CONNECTOR_TYPE}/configs")
            assert resp.status_code == 200
            items = resp.json()
            created = next((i for i in items if i.get("id") == item_id), None)
            assert created is not None
            masked_token = created.get("access_token")
            assert masked_token in ("********", None, "")
            assert created.get("search_filters") == {
                "props.application-context": "production",
                "props.division": "engineering",
            }

            print("Step 11: PUT /api/v1/connectors/{connector_type}/configs/{id} (update)")
            update_payload = {
                "url": f"https://github.com/example/{marker}-updated",
                "access_token": f"token-{marker}-updated",
                "search_filters": {
                    "props.application-context": "staging",
                    "props.asset-classification": "confidential",
                },
                "branch_name_patterns": ["main", "develop"],
                "extraction_sources": ["branch", "commit_message"],
            }
            resp = await ac.put(
                f"/api/v1/connectors/{CONNECTOR_TYPE}/configs/{item_id}",
                json=update_payload,
            )
            assert resp.status_code == 200

            print("Step 12: DELETE /api/v1/connectors/{connector_type}/configs/{id} (delete)")
            resp = await ac.delete(
                f"/api/v1/connectors/{CONNECTOR_TYPE}/configs/{item_id}"
            )
            assert resp.status_code == 200
            created_item_ids.remove(item_id)

            print("Step 13: POST /api/v1/connectors/{connector_type}/test")
            resp = await ac.post(f"/api/v1/connectors/{CONNECTOR_TYPE}/test")
            assert resp.status_code == 200
            assert "success" in resp.json()

            if not initial_items:
                print("Step 14: DELETE /api/v1/connectors/{connector_type} (no pre-existing items)")
                resp = await ac.delete(f"/api/v1/connectors/{CONNECTOR_TYPE}")
                assert resp.status_code == 200
        finally:
            print("Cleanup: deleting created config items (if any)")
            for item_id in list(created_item_ids):
                await ac.delete(
                    f"/api/v1/connectors/{CONNECTOR_TYPE}/configs/{item_id}"
                )
            if changed_config:
                print("Cleanup: restoring connector config")
                restore_config = original_config if original_config is not None else None
                await ac.patch(
                    f"/api/v1/connectors/{CONNECTOR_TYPE}",
                    json={"config": restore_config},
                )


@pytest.mark.asyncio
@pytest.mark.skip(reason="Disabled: modifies Atlassian MCP connector DB state")
async def test_atlassian_mcp_connector_config_api():
    changed_config = False
    original_config = None
    marker = _marker_value()

    async with httpx.AsyncClient(base_url=BASE_URL) as ac:
        try:
            print("Atlassian MCP Step 1: GET /api/v1/connectors/{connector_type}")
            resp = await ac.get(
                f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}",
                params={"include_secrets": "true"},
            )
            assert resp.status_code == 200
            original_config = resp.json().get("config")

            print("Atlassian MCP Step 2: PATCH /api/v1/connectors/{connector_type} (set config)")
            create_payload = {
                "enabled": True,
                "server_url": "https://mcp.atlassian.com/v1/mcp",
                "token": f"atlassian-token-{marker}",
                "__test_marker": marker,
            }
            resp = await ac.patch(
                f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}",
                json={"config": create_payload},
            )
            assert resp.status_code == 200
            changed_config = True
            returned_config = resp.json().get("config", {})
            assert returned_config.get("enabled") is True
            assert returned_config.get("server_url") == "https://mcp.atlassian.com/v1/mcp"
            assert returned_config.get("token") == "********"
            assert returned_config.get("__test_marker") is None
            assert "encrypted_token" not in returned_config

            print("Atlassian MCP Step 3: GET masked config")
            resp = await ac.get(f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}")
            assert resp.status_code == 200
            masked_config = resp.json().get("config", {})
            assert masked_config.get("token") == "********"
            assert masked_config.get("server_url") == "https://mcp.atlassian.com/v1/mcp"
            assert "encrypted_token" not in masked_config

            print("Atlassian MCP Step 3b: GET /api/v1/connectors/ (masked in list view)")
            resp = await ac.get("/api/v1/connectors/")
            assert resp.status_code == 200
            connectors = resp.json()
            atlassian_mcp = next(
                (connector for connector in connectors if connector.get("connector_type") == ATLASSIAN_MCP_CONNECTOR_TYPE),
                None,
            )
            assert atlassian_mcp is not None
            list_config = atlassian_mcp.get("config", {})
            assert list_config.get("token") == "********"
            assert "encrypted_token" not in list_config

            print("Atlassian MCP Step 4: GET config with include_secrets=true")
            resp = await ac.get(
                f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}",
                params={"include_secrets": "true"},
            )
            assert resp.status_code == 200
            secret_config = resp.json().get("config", {})
            assert secret_config.get("token") == f"atlassian-token-{marker}"
            assert secret_config.get("server_url") == "https://mcp.atlassian.com/v1/mcp"
            assert "encrypted_token" not in secret_config

            print("Atlassian MCP Step 5: PATCH without token should preserve secret")
            update_payload = {
                "enabled": True,
                "server_url": "https://mcp.atlassian.com/v1/mcp",
            }
            resp = await ac.patch(
                f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}",
                json={"config": update_payload},
            )
            assert resp.status_code == 200
            changed_config = True
            returned_config = resp.json().get("config", {})
            assert returned_config.get("token") == "********"

            print("Atlassian MCP Step 6: GET config with include_secrets=true (verify preserved secret)")
            resp = await ac.get(
                f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}",
                params={"include_secrets": "true"},
            )
            assert resp.status_code == 200
            secret_config = resp.json().get("config", {})
            assert secret_config.get("token") == f"atlassian-token-{marker}"

            print("Atlassian MCP Step 7: PATCH enabled config without server_url should fail")
            resp = await ac.patch(
                f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}",
                json={"config": {"enabled": True}},
            )
            assert resp.status_code == 400
        finally:
            if changed_config:
                print("Cleanup: restoring Atlassian MCP connector config")
                restore_config = original_config if original_config is not None else None
                await ac.patch(
                    f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}",
                    json={"config": restore_config},
                )


@pytest.mark.asyncio
@pytest.mark.skip(reason="Disabled: clears Atlassian MCP connector DB state")
async def test_atlassian_mcp_clear_connector_config():
    marker = _marker_value()

    async with httpx.AsyncClient(base_url=BASE_URL) as ac:
        # Save a config with a secret so there is something to clear
        print("Clear Test Step 1: PATCH to save config with token")
        resp = await ac.patch(
            f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}",
            json={"config": {
                "enabled": True,
                "server_url": "https://mcp.atlassian.com/v1/mcp",
                "token": f"clear-test-token-{marker}",
            }},
        )
        assert resp.status_code == 200
        assert resp.json().get("config", {}).get("token") == "********"

        # Clear the config
        print("Clear Test Step 2: DELETE /config to wipe all connector-level config")
        resp = await ac.delete(f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}/config")
        assert resp.status_code == 200
        cleared_config = resp.json().get("config") or {}
        assert cleared_config.get("token") in (None, "")
        assert "encrypted_token" not in cleared_config
        # Confirm the secret is gone via include_secrets
        print("Clear Test Step 3: GET with include_secrets=true confirms token is gone")
        resp = await ac.get(
            f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}",
            params={"include_secrets": "true"},
        )
        assert resp.status_code == 200
        secret_config = resp.json().get("config") or {}
        assert secret_config.get("token") is None

        # Confirm re-enable now requires a token (first-save enforcement)
        print("Clear Test Step 4: PATCH enabled without token after clear should fail")
        resp = await ac.patch(
            f"/api/v1/connectors/{ATLASSIAN_MCP_CONNECTOR_TYPE}",
            json={"config": {
                "enabled": True,
                "server_url": "https://mcp.atlassian.com/v1/mcp",
            }},
        )
        assert resp.status_code == 400
