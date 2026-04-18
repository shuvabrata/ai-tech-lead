import pytest
import httpx


pytestmark = [pytest.mark.integration, pytest.mark.server]

@pytest.mark.asyncio
async def test_projects_crud():
    base_url = "http://localhost:8000"
    async with httpx.AsyncClient(base_url=base_url) as ac:
        # Create project
        resp = await ac.post("/api/v1/projects/", json={"name": "Test Project", "description": "desc"})
        assert resp.status_code == 200
        data = resp.json()
        project_id = data["id"]
        assert data["name"] == "Test Project"

        # Get all projects
        resp = await ac.get("/api/v1/projects/")
        assert resp.status_code == 200
        assert any(p["id"] == project_id for p in resp.json())

        # Get single project
        resp = await ac.get(f"/api/v1/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == project_id

        # Update project
        resp = await ac.put(f"/api/v1/projects/{project_id}", json={"name": "Updated", "description": "new desc"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

        # Delete project
        resp = await ac.delete(f"/api/v1/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Confirm deletion
        resp = await ac.get(f"/api/v1/projects/{project_id}")
        assert resp.status_code == 404
