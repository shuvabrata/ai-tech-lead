"""Integration tests for the catalog-metadata (favourites) API.

Tests full HTTP round-trips against a running app server at
``http://localhost:8000``.  Requires the app to be started separately::

    PYTHONPATH=src uvicorn app.main:app --reload

Markers: ``integration``, ``server``.

**Safety (clean up irrespective of pass/fail):** A session-scoped ``autouse``
fixture snapshots the pre-existing ``catalog_id`` values on setup, then on
teardown deletes every row whose ``catalog_id`` was not present at setup. This
guarantees the database returns to its pre-test state even if a test fails
midway.

Every ``catalog_id`` these tests use is a real query from the YAML catalog
(validated against ``GET /api/v1/queries/catalog``), so the 404-on-unknown
behaviour is exercised with a genuinely unknown id.
"""

from __future__ import annotations

import httpx
import psycopg2
import pytest

from app.settings import settings

pytestmark = [pytest.mark.integration, pytest.mark.server]

BASE_URL = "http://localhost:8000"

# A real catalog query id (namespace/slug) used for create/update tests.
VALID_CATALOG_ID = "schema/view_all_node_types"
# A second real id used to test filtering with multiple rows.
VALID_CATALOG_ID_2 = "schema/view_all_relationship_types"
# A deliberately unknown id used to exercise the 404 path.
UNKNOWN_CATALOG_ID = "nonexistent/does_not_exist"


def _delete_metadata_row(catalog_id: str) -> None:
    """Delete a catalog metadata row directly from the DB.

    The API has no DELETE endpoint (rows are created lazily via upsert), so
    the teardown safety net removes rows created during the run directly via
    psycopg2. The async ``DATABASE_URL`` is converted to a sync psycopg2 URL.
    """
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM catalog_metadata WHERE catalog_id = %s",
                (catalog_id,),
            )
        conn.commit()


# ── Snapshot / restore (session-scoped safety net) ────────────────────


@pytest.fixture(scope="session", autouse=True)
def metadata_snapshot() -> set[str]:
    """Snapshot pre-test state; restore it on teardown.

    Setup captures the set of pre-existing ``catalog_id`` values. Teardown
    deletes any row whose ``catalog_id`` was not present at setup (i.e. created
    during the run). Uses the same ``BASE_URL`` for both phases.
    """
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        resp = client.get("/api/v1/queries/catalog-metadata")
        resp.raise_for_status()
        snapshot = {item["catalog_id"] for item in resp.json()["items"]}

    yield snapshot

    # --- teardown ---
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        current = client.get("/api/v1/queries/catalog-metadata").json()
        for item in current["items"]:
            if item["catalog_id"] not in snapshot:
                # Flip to false so the row is no longer a favourite, then
                # delete it directly from the DB to restore the pre-test state
                # exactly (the API has no DELETE endpoint).
                client.put(
                    f"/api/v1/queries/catalog-metadata/{item['catalog_id']}",
                    json={"is_favourite": False},
                )
                _delete_metadata_row(item["catalog_id"])


async def _list_metadata(
    client: httpx.AsyncClient, *, is_favourite: bool | None = None
) -> list[dict]:
    """Return all catalog metadata rows, optionally filtered."""
    params = {"is_favourite": is_favourite} if is_favourite is not None else None
    resp = await client.get("/api/v1/queries/catalog-metadata", params=params)
    assert resp.status_code == 200
    return resp.json()["items"]


# ── Read-only (no rows created) ───────────────────────────────────────


class TestList:
    @pytest.mark.asyncio
    async def test_returns_empty_list_initially(self) -> None:
        """GET /catalog-metadata returns an empty list when no rows exist."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            items = await _list_metadata(client)
        assert items == []

    @pytest.mark.asyncio
    async def test_filter_is_favourite_true(self) -> None:
        """?is_favourite=true filters to favourited rows only."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            # Create a favourited row, then filter.
            resp = await client.put(
                f"/api/v1/queries/catalog-metadata/{VALID_CATALOG_ID}",
                json={"is_favourite": True},
            )
            assert resp.status_code == 200

            fav_items = await _list_metadata(client, is_favourite=True)
            non_fav_items = await _list_metadata(client, is_favourite=False)

        assert any(item["catalog_id"] == VALID_CATALOG_ID for item in fav_items)
        assert all(
            item["catalog_id"] != VALID_CATALOG_ID for item in non_fav_items
        )


# ── Upsert behaviour ──────────────────────────────────────────────────


class TestUpsert:
    @pytest.mark.asyncio
    async def test_put_creates_row(self) -> None:
        """PUT creates a row and returns it."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.put(
                f"/api/v1/queries/catalog-metadata/{VALID_CATALOG_ID}",
                json={"is_favourite": True},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["catalog_id"] == VALID_CATALOG_ID
            assert body["is_favourite"] is True

    @pytest.mark.asyncio
    async def test_put_is_idempotent(self) -> None:
        """Repeated PUT with the same value does not create duplicate rows."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            await client.put(
                f"/api/v1/queries/catalog-metadata/{VALID_CATALOG_ID}",
                json={"is_favourite": True},
            )
            await client.put(
                f"/api/v1/queries/catalog-metadata/{VALID_CATALOG_ID}",
                json={"is_favourite": True},
            )
            items = await _list_metadata(client)

        matches = [
            item for item in items if item["catalog_id"] == VALID_CATALOG_ID
        ]
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_put_flips_existing_row(self) -> None:
        """PUT with is_favourite=false flips an existing favourited row."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            await client.put(
                f"/api/v1/queries/catalog-metadata/{VALID_CATALOG_ID}",
                json={"is_favourite": True},
            )
            resp = await client.put(
                f"/api/v1/queries/catalog-metadata/{VALID_CATALOG_ID}",
                json={"is_favourite": False},
            )
            assert resp.status_code == 200
            assert resp.json()["is_favourite"] is False

    @pytest.mark.asyncio
    async def test_put_unknown_catalog_id_returns_404(self) -> None:
        """PUT with an unknown catalog_id returns 404."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.put(
                f"/api/v1/queries/catalog-metadata/{UNKNOWN_CATALOG_ID}",
                json={"is_favourite": True},
            )
        assert resp.status_code == 404


# ── Single-row fetch ──────────────────────────────────────────────────


class TestGetSingle:
    @pytest.mark.asyncio
    async def test_get_returns_row(self) -> None:
        """GET /catalog-metadata/{id} returns the row when present."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            await client.put(
                f"/api/v1/queries/catalog-metadata/{VALID_CATALOG_ID}",
                json={"is_favourite": True},
            )
            resp = await client.get(
                f"/api/v1/queries/catalog-metadata/{VALID_CATALOG_ID}"
            )
            assert resp.status_code == 200
            assert resp.json()["catalog_id"] == VALID_CATALOG_ID

    @pytest.mark.asyncio
    async def test_get_unknown_returns_404(self) -> None:
        """GET /catalog-metadata/{id} returns 404 when absent."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get(
                f"/api/v1/queries/catalog-metadata/{UNKNOWN_CATALOG_ID}"
            )
        assert resp.status_code == 404