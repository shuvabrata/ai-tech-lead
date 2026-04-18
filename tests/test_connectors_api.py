import uuid

import httpx
import pytest


BASE_URL = "http://localhost:8000"
CONNECTOR_TYPE = "github"


pytestmark = [pytest.mark.integration, pytest.mark.server]


def _marker_value() -> str:
    return f"integration-{uuid.uuid4()}"


@pytest.mark.asyncio
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

            print("Step 8: POST /api/v1/connectors/{connector_type}/configs (create)")
            create_payload = {
                "url": f"https://github.com/example/{marker}",
                "access_token": f"token-{marker}",
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

            print("Step 9: GET /api/v1/connectors/{connector_type}/configs (verify mask)")
            resp = await ac.get(f"/api/v1/connectors/{CONNECTOR_TYPE}/configs")
            assert resp.status_code == 200
            items = resp.json()
            created = next((i for i in items if i.get("id") == item_id), None)
            assert created is not None
            masked_token = created.get("access_token")
            assert masked_token in ("********", None, "")

            print("Step 10: PUT /api/v1/connectors/{connector_type}/configs/{id} (update)")
            update_payload = {
                "url": f"https://github.com/example/{marker}-updated",
                "access_token": f"token-{marker}-updated",
                "branch_name_patterns": ["main", "develop"],
                "extraction_sources": ["branch", "commit_message"],
            }
            resp = await ac.put(
                f"/api/v1/connectors/{CONNECTOR_TYPE}/configs/{item_id}",
                json=update_payload,
            )
            assert resp.status_code == 200

            print("Step 11: DELETE /api/v1/connectors/{connector_type}/configs/{id} (delete)")
            resp = await ac.delete(
                f"/api/v1/connectors/{CONNECTOR_TYPE}/configs/{item_id}"
            )
            assert resp.status_code == 200
            created_item_ids.remove(item_id)

            print("Step 12: POST /api/v1/connectors/{connector_type}/test")
            resp = await ac.post(f"/api/v1/connectors/{CONNECTOR_TYPE}/test")
            assert resp.status_code == 200
            assert "success" in resp.json()

            if not initial_items:
                print("Step 13: DELETE /api/v1/connectors/{connector_type} (no pre-existing items)")
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
