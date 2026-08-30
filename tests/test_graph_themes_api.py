"""Integration tests for the graph-themes API.

Tests full HTTP round-trips against a running app server at
``http://localhost:8000``.  Requires the app to be started separately::

    PYTHONPATH=src uvicorn app.main:app --reload

Markers: ``integration``, ``server``.

**Safety (clean up irrespective of pass/fail):** A session-scoped ``autouse``
fixture snapshots the pre-existing theme rows and the current default theme per
base mode on setup, then on teardown deletes every row created during the run
and restores the original defaults. This guarantees the database returns to its
pre-test state even if a test fails midway.

Every theme these tests create has the literal substring ``test`` in its name
so any leaked rows are both greppable and unambiguous.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.server]

BASE_URL = "http://localhost:8000"


# ── Snapshot / restore (session-scoped safety net) ────────────────────


@pytest.fixture(scope="session", autouse=True)
def themes_snapshot() -> dict:
    """Snapshot pre-test state; restore it on teardown.

    Setup captures the set of pre-existing theme ids and the id of the current
    default theme per base mode. Teardown deletes any theme whose id was not
    present at setup (i.e. created during the run) and re-sets each base mode's
    original default. Uses the same ``BASE_URL`` for both phases.
    """
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        resp = client.get("/api/v1/graph-themes/")
        resp.raise_for_status()
        themes = resp.json()
        snapshot = {
            "ids": {t["id"] for t in themes},
            "defaults": {t["base_theme"]: t["id"] for t in themes if t["is_default"]},
        }

    yield snapshot

    # --- teardown ---
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        current = client.get("/api/v1/graph-themes/").json()
        for theme in current:
            if theme["id"] not in snapshot["ids"]:
                client.delete(f"/api/v1/graph-themes/{theme['id']}")

        for _base, theme_id in snapshot["defaults"].items():
            client.post(f"/api/v1/graph-themes/{theme_id}/set-default")


async def _list_themes(client: httpx.AsyncClient) -> list[dict]:
    """Return all themes from the live server."""
    resp = await client.get("/api/v1/graph-themes/")
    assert resp.status_code == 200
    return resp.json()


# ── Read-only (no rows created) ───────────────────────────────────────


class TestListAndEffective:
    @pytest.mark.asyncio
    async def test_returns_seeded_themes(self) -> None:
        """GET returns the 4 seeded builtin themes."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            themes = await _list_themes(client)
        assert len(themes) >= 4
        names = {t["name"] for t in themes}
        assert {"Default", "Ocean Light", "Midnight Dark"} <= names

    @pytest.mark.asyncio
    async def test_default_anchors_are_default(self) -> None:
        """Each base mode has exactly one default theme."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            themes = await _list_themes(client)
        for base in ("executive-light", "executive-dark"):
            defaults = [t for t in themes if t["base_theme"] == base and t["is_default"]]
            assert len(defaults) == 1

    @pytest.mark.asyncio
    async def test_effective_returns_merged_tokens(self) -> None:
        """GET /effective returns base ⊕ default-theme overrides (Cytoscape keys)."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get(
                "/api/v1/graph-themes/effective",
                params={"base_theme": "executive-light"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["base_theme"] == "executive-light"
        assert "nodes" in data and "edges" in data and "global" in data
        assert "background-color" in data["nodes"]["Person"]

    @pytest.mark.asyncio
    async def test_effective_unknown_base_rejected(self) -> None:
        """An unknown base_theme returns 422."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get(
                "/api/v1/graph-themes/effective",
                params={"base_theme": "executive-solar"},
            )
        assert resp.status_code == 422


# ── CRUD round-trip (creates + cleans a "test" row) ───────────────────


class TestCrudRoundTrip:
    @pytest.mark.asyncio
    async def test_create_list_patch_delete(self) -> None:
        """POST create → GET list → PATCH → DELETE round-trip."""
        payload = {
            "name": "test-roundtrip",
            "base_theme": "executive-light",
            "overrides": {
                "nodes": {"Person": {"color": "#0EA5E9", "shape": "octagon"}},
                "edges": {"line_color": "#94A3B8"},
                "global": {"node_label_color": "#0F172A"},
            },
        }
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            # Create
            resp = await client.post("/api/v1/graph-themes/", json=payload)
            assert resp.status_code == 201
            created = resp.json()
            theme_id = created["id"]
            assert created["source"] == "user"
            assert created["is_default"] is False

            try:
                # List contains it
                assert any(t["id"] == theme_id for t in await _list_themes(client))

                # Patch
                resp = await client.patch(
                    f"/api/v1/graph-themes/{theme_id}",
                    json={"name": "test-roundtrip-renamed"},
                )
                assert resp.status_code == 200
                assert resp.json()["name"] == "test-roundtrip-renamed"
            finally:
                # Delete (idempotent; also covered by the session net).
                await client.delete(f"/api/v1/graph-themes/{theme_id}")

            # Gone
            resp = await client.get(f"/api/v1/graph-themes/{theme_id}")
            assert resp.status_code == 404


# ── Validation (no persisted rows) ────────────────────────────────────


class TestValidation:
    @pytest.mark.asyncio
    async def test_invalid_hex_rejected(self) -> None:
        """A non-hex colour is rejected with 422 before any write."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.post(
                "/api/v1/graph-themes/",
                json={
                    "name": "test-bad-color",
                    "base_theme": "executive-light",
                    "overrides": {"nodes": {"Person": {"color": "red"}}},
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_shape_rejected(self) -> None:
        """An unknown shape is rejected with 422."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.post(
                "/api/v1/graph-themes/",
                json={
                    "name": "test-bad-shape",
                    "base_theme": "executive-light",
                    "overrides": {"nodes": {"Person": {"shape": "blob"}}},
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_width_rejected(self) -> None:
        """A negative width is rejected with 422."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.post(
                "/api/v1/graph-themes/",
                json={
                    "name": "test-bad-width",
                    "base_theme": "executive-light",
                    "overrides": {"nodes": {"Person": {"width": -5}}},
                },
            )
        assert resp.status_code == 422


# ── Builtin immutability (read-only; no rows created) ────────────────


class TestBuiltinImmutability:
    @pytest.mark.asyncio
    async def test_patch_builtin_returns_409(self) -> None:
        """PATCH on a builtin theme returns 409."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            builtin = next(t for t in await _list_themes(client) if t["source"] == "builtin")
            resp = await client.patch(
                f"/api/v1/graph-themes/{builtin['id']}",
                json={"name": "test-hacked"},
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_builtin_returns_409(self) -> None:
        """DELETE on a builtin theme returns 409."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            builtin = next(t for t in await _list_themes(client) if t["source"] == "builtin")
            resp = await client.delete(f"/api/v1/graph-themes/{builtin['id']}")
        assert resp.status_code == 409


# ── Clone (creates a copy; deleted via id + session net) ─────────────


class TestClone:
    @pytest.mark.asyncio
    async def test_clone_builtin_creates_user_row(self) -> None:
        """Cloning a builtin produces a new editable user row."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            builtin = next(t for t in await _list_themes(client) if t["source"] == "builtin")
            resp = await client.post(f"/api/v1/graph-themes/{builtin['id']}/clone")
            assert resp.status_code == 201
            clone = resp.json()
            clone_id = clone["id"]
            try:
                assert clone["source"] == "user"
                assert clone["name"] == f"{builtin['name']} (copy)"
                assert clone["is_default"] is False
            finally:
                # Clone name lacks "test", so delete by id explicitly.
                await client.delete(f"/api/v1/graph-themes/{clone_id}")


# ── Set default (temporarily swaps; restores builtin anchor) ─────────


class TestSetDefault:
    @pytest.mark.asyncio
    async def test_set_default_swaps_and_restores(self) -> None:
        """Setting a test theme default clears the old one; restore afterwards."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            themes = await _list_themes(client)
            light = [t for t in themes if t["base_theme"] == "executive-light"]
            original_default = next(t for t in light if t["is_default"])

            # Create a candidate test theme.
            resp = await client.post(
                "/api/v1/graph-themes/",
                json={"name": "test-set-default-candidate", "base_theme": "executive-light"},
            )
            assert resp.status_code == 201
            candidate_id = resp.json()["id"]

            try:
                # Make the candidate the default.
                resp = await client.post(
                    f"/api/v1/graph-themes/{candidate_id}/set-default"
                )
                assert resp.status_code == 200
                assert resp.json()["is_default"] is True

                # Single-default invariant: the original is no longer default.
                themes = await _list_themes(client)
                light = [t for t in themes if t["base_theme"] == "executive-light"]
                defaults = [t for t in light if t["is_default"]]
                assert len(defaults) == 1
                assert defaults[0]["id"] == candidate_id
            finally:
                # Restore the original default and remove the candidate.
                await client.post(
                    f"/api/v1/graph-themes/{original_default['id']}/set-default"
                )
                await client.delete(f"/api/v1/graph-themes/{candidate_id}")

            # Confirm the builtin anchor is default again.
            themes = await _list_themes(client)
            light = [t for t in themes if t["base_theme"] == "executive-light"]
            defaults = [t for t in light if t["is_default"]]
            assert defaults[0]["id"] == original_default["id"]


# ── PATCH base_theme (re-snapshot + default-orphaning guard) ─────────


class TestUpdateBaseTheme:
    """PATCHing ``base_theme`` re-snapshots against the new base and guards
    against orphaning a default.

    Cleanup: every row created here carries the ``test`` substring in its name
    and is deleted in a ``finally``; the session-scoped ``themes_snapshot``
    fixture additionally restores the pre-test defaults and removes any leaked
    rows regardless of pass/fail.
    """

    @pytest.mark.asyncio
    async def test_base_theme_change_resnapshots_against_new_base(self) -> None:
        """PATCHing only ``base_theme`` re-materializes the stored snapshot.

        The stored snapshot is a full document frozen to the *old* base's
        palette. Changing ``base_theme`` must re-snapshot the existing
        overrides against the **new** base so the theme actually renders with
        the new palette. Fields that differ between the light and dark bases
        (the untyped ``default`` node colour and the global ``selection_color``)
        must reflect the dark base after the PATCH.
        """
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            # Create a light-base theme with a distinctive Person override.
            resp = await client.post(
                "/api/v1/graph-themes/",
                json={
                    "name": "test-base-change",
                    "base_theme": "executive-light",
                    "overrides": {
                        "nodes": {"Person": {"color": "#123456"}},
                    },
                },
            )
            assert resp.status_code == 201
            theme_id = resp.json()["id"]

            try:
                # Sanity: the light snapshot froze the light base's default
                # node colour and selection colour.
                created = resp.json()
                assert created["overrides"]["nodes"]["default"]["color"] == "#B8B8B8"
                assert created["overrides"]["global"]["selection_color"] == "#424242"

                # PATCH only base_theme → dark.
                resp = await client.patch(
                    f"/api/v1/graph-themes/{theme_id}",
                    json={"base_theme": "executive-dark"},
                )
                assert resp.status_code == 200
                updated = resp.json()

                # The base column changed...
                assert updated["base_theme"] == "executive-dark"
                # ...and the snapshot was re-materialized against the dark base:
                # the default node colour and selection colour now reflect dark.
                assert updated["overrides"]["nodes"]["default"]["color"] == "#7f8fa3"
                assert updated["overrides"]["global"]["selection_color"] == "#d5deea"
                # The user's Person override survives the re-snapshot.
                assert updated["overrides"]["nodes"]["Person"]["color"] == "#123456"
            finally:
                await client.delete(f"/api/v1/graph-themes/{theme_id}")

    @pytest.mark.asyncio
    async def test_base_theme_change_on_default_returns_409(self) -> None:
        """Moving a default theme to another base mode is rejected (409).

        Otherwise the old base mode would be silently left with no default —
        the exact fallback-to-hardcoded-palette state that the delete guard
        exists to prevent. The guard must fire before any mutation.
        """
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            # Capture the current light default BEFORE the swap so cleanup can
            # restore it (after the swap, the candidate is the default).
            themes = await _list_themes(client)
            light = [t for t in themes if t["base_theme"] == "executive-light"]
            original_default = next(t for t in light if t["is_default"])

            # Create a candidate and make it the default for light.
            resp = await client.post(
                "/api/v1/graph-themes/",
                json={"name": "test-base-change-default", "base_theme": "executive-light"},
            )
            assert resp.status_code == 201
            theme_id = resp.json()["id"]

            try:
                resp = await client.post(f"/api/v1/graph-themes/{theme_id}/set-default")
                assert resp.status_code == 200

                # PATCHing base_theme on the default must be rejected.
                resp = await client.patch(
                    f"/api/v1/graph-themes/{theme_id}",
                    json={"base_theme": "executive-dark"},
                )
                assert resp.status_code == 409

                # The theme is unchanged: still light, still the default.
                resp = await client.get(f"/api/v1/graph-themes/{theme_id}")
                assert resp.status_code == 200
                theme = resp.json()
                assert theme["base_theme"] == "executive-light"
                assert theme["is_default"] is True
            finally:
                # Restore the original light default, then remove the candidate.
                await client.post(
                    f"/api/v1/graph-themes/{original_default['id']}/set-default"
                )
                await client.delete(f"/api/v1/graph-themes/{theme_id}")

    @pytest.mark.asyncio
    async def test_base_theme_same_value_is_noop(self) -> None:
        """PATCHing ``base_theme`` with the current value is a no-op.

        No re-snapshot occurs and no error is raised; the stored snapshot is
        left untouched.
        """
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.post(
                "/api/v1/graph-themes/",
                json={
                    "name": "test-base-noop",
                    "base_theme": "executive-light",
                    "overrides": {
                        "nodes": {"Person": {"color": "#123456"}},
                    },
                },
            )
            assert resp.status_code == 201
            theme_id = resp.json()["id"]
            original_overrides = resp.json()["overrides"]

            try:
                resp = await client.patch(
                    f"/api/v1/graph-themes/{theme_id}",
                    json={"base_theme": "executive-light"},
                )
                assert resp.status_code == 200
                updated = resp.json()
                assert updated["base_theme"] == "executive-light"
                # Snapshot untouched (still the light base's default node colour).
                assert updated["overrides"]["nodes"]["default"]["color"] == "#B8B8B8"
                assert updated["overrides"] == original_overrides
            finally:
                await client.delete(f"/api/v1/graph-themes/{theme_id}")