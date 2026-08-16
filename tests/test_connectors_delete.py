"""Unit tests for connector delete confirmation callbacks.

Tests cover:
  - ``confirm_item_delete`` — shows dialog, captures target in Store
  - ``handle_item_delete`` — deletes item via API, returns updated stores
  - ``confirm_connector_delete`` — shows dialog, captures target in Store
  - ``handle_connector_delete`` — deletes connector config via API, navigates away
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from dash import no_update
from dash.exceptions import PreventUpdate

from app.dash_app.pages.connectors.callbacks import (
    confirm_connector_delete,
    confirm_item_delete,
    handle_connector_delete,
    handle_item_delete,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# confirm_item_delete
# ---------------------------------------------------------------------------


class TestConfirmItemDelete:
    """Tests for ``confirm_item_delete()``."""

    def test_no_clicks_raises_prevent_update(self) -> None:
        """All None clicks → PreventUpdate (dialog stays hidden)."""
        with pytest.raises(PreventUpdate):
            confirm_item_delete([None, None])

    def test_click_shows_dialog_and_captures_target(self) -> None:
        """A click on a delete button shows the dialog and stores the target."""
        with patch(
            "app.dash_app.pages.connectors.callbacks.callback_context"
        ) as mock_ctx:
            mock_ctx.triggered_id = {
                "type": "connector-item-delete",
                "connector_type": "github",
                "item_id": "42",
            }
            displayed, target = confirm_item_delete([1, None])

        assert displayed is True
        assert target == {"connector_type": "github", "item_id": "42"}

    def test_triggered_id_not_dict_raises_prevent_update(self) -> None:
        """If triggered_id is not a dict, raise PreventUpdate."""
        with patch(
            "app.dash_app.pages.connectors.callbacks.callback_context"
        ) as mock_ctx:
            mock_ctx.triggered_id = "not-a-dict"
            with pytest.raises(PreventUpdate):
                confirm_item_delete([1])


# ---------------------------------------------------------------------------
# handle_item_delete
# ---------------------------------------------------------------------------


class TestHandleItemDelete:
    """Tests for ``handle_item_delete()``."""

    def test_no_submit_clicks_raises_prevent_update(self) -> None:
        """submit_n_clicks is None → PreventUpdate."""
        with pytest.raises(PreventUpdate):
            handle_item_delete(None, {"connector_type": "github", "item_id": "42"})

    def test_null_target_returns_no_update(self) -> None:
        """Target is None → all no_update, dialog hidden."""
        result = handle_item_delete(1, None)
        assert result == (no_update, no_update, no_update, False)

    def test_missing_connector_type_returns_no_update(self) -> None:
        """Target missing connector_type → all no_update."""
        result = handle_item_delete(1, {"item_id": "42"})
        assert result == (no_update, no_update, no_update, False)

    def test_missing_item_id_returns_no_update(self) -> None:
        """Target missing item_id → all no_update."""
        result = handle_item_delete(1, {"connector_type": "github"})
        assert result == (no_update, no_update, no_update, False)

    def test_successful_delete(self) -> None:
        """Happy path: DELETE succeeds, items reloaded, success alert returned."""
        mock_delete_resp = MagicMock()
        mock_delete_resp.raise_for_status.return_value = None

        mock_items_resp = MagicMock()
        mock_items_resp.raise_for_status.return_value = None
        mock_items_resp.json.return_value = [
            {"id": "1", "name": "other-repo"}
        ]

        with patch(
            "app.dash_app.pages.connectors.callbacks.requests.delete",
            return_value=mock_delete_resp,
        ), patch(
            "app.dash_app.pages.connectors.callbacks.requests.get",
            return_value=mock_items_resp,
        ):
            store, edit, alert, dialog = handle_item_delete(
                1, {"connector_type": "github", "item_id": "42"}
            )

        assert store["status"] == "ok"
        assert store["items"] == [{"id": "1", "name": "other-repo"}]
        assert edit["action"] == "clear"
        assert "deleted" in str(alert).lower()
        assert dialog is False

    def test_delete_request_failure(self) -> None:
        """DELETE raises RequestException → error alert, stores unchanged."""
        import requests as req_lib

        with patch(
            "app.dash_app.pages.connectors.callbacks.requests.delete",
            side_effect=req_lib.RequestException("Connection refused"),
        ):
            store, edit, alert, dialog = handle_item_delete(
                1, {"connector_type": "github", "item_id": "42"}
            )

        assert store is no_update
        assert edit is no_update
        assert "Failed to delete" in str(alert)
        assert dialog is False


# ---------------------------------------------------------------------------
# confirm_connector_delete
# ---------------------------------------------------------------------------


class TestConfirmConnectorDelete:
    """Tests for ``confirm_connector_delete()``."""

    def test_no_clicks_raises_prevent_update(self) -> None:
        """All None clicks → PreventUpdate."""
        with pytest.raises(PreventUpdate):
            confirm_connector_delete([None])

    def test_click_shows_dialog_and_captures_target(self) -> None:
        """A click shows the dialog and stores the connector type."""
        with patch(
            "app.dash_app.pages.connectors.callbacks.callback_context"
        ) as mock_ctx:
            mock_ctx.triggered_id = {
                "type": "connector-delete",
                "connector_type": "github",
            }
            displayed, target = confirm_connector_delete([1])

        assert displayed is True
        assert target == {"connector_type": "github"}

    def test_triggered_id_not_dict_raises_prevent_update(self) -> None:
        """If triggered_id is not a dict, raise PreventUpdate."""
        with patch(
            "app.dash_app.pages.connectors.callbacks.callback_context"
        ) as mock_ctx:
            mock_ctx.triggered_id = "not-a-dict"
            with pytest.raises(PreventUpdate):
                confirm_connector_delete([1])


# ---------------------------------------------------------------------------
# handle_connector_delete
# ---------------------------------------------------------------------------


class TestHandleConnectorDelete:
    """Tests for ``handle_connector_delete()``."""

    def test_no_submit_clicks_raises_prevent_update(self) -> None:
        """submit_n_clicks is None → PreventUpdate."""
        with pytest.raises(PreventUpdate):
            handle_connector_delete(None, {"connector_type": "github"})

    def test_null_target_returns_no_update(self) -> None:
        """Target is None → all no_update, dialog hidden."""
        result = handle_connector_delete(1, None)
        assert result == (no_update, no_update, no_update, no_update, False)

    def test_missing_connector_type_returns_no_update(self) -> None:
        """Target missing connector_type → all no_update."""
        result = handle_connector_delete(1, {})
        assert result == (no_update, no_update, no_update, no_update, False)

    def test_successful_delete(self) -> None:
        """Happy path: DELETE succeeds, stores cleared, navigates to list."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None

        with patch(
            "app.dash_app.pages.connectors.callbacks.requests.delete",
            return_value=mock_resp,
        ):
            detail, items, alert, pathname, dialog = handle_connector_delete(
                1, {"connector_type": "github"}
            )

        assert detail["status"] == "ok"
        assert items["items"] == []
        assert "deleted" in str(alert).lower()
        assert pathname == "/app/connectors"
        assert dialog is False

    def test_delete_request_failure(self) -> None:
        """DELETE raises RequestException → error alert, no navigation."""
        import requests as req_lib

        with patch(
            "app.dash_app.pages.connectors.callbacks.requests.delete",
            side_effect=req_lib.RequestException("Connection refused"),
        ):
            detail, items, alert, pathname, dialog = handle_connector_delete(
                1, {"connector_type": "github"}
            )

        assert detail is no_update
        assert items is no_update
        assert "Delete failed" in str(alert)
        assert pathname is no_update
        assert dialog is False
