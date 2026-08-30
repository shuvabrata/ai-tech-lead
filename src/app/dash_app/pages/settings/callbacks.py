"""Callbacks for the Settings hub page."""

from __future__ import annotations

from typing import Any

from dash import ALL, Input, Output, callback, callback_context
from dash.exceptions import PreventUpdate


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Input({"type": "settings-card", "card_id": ALL}, "n_clicks_timestamp"),
    prevent_initial_call=True,
)
def handle_card_click(_timestamps: list[int | None]) -> Any:
    """Navigate to the sub-page when a clickable settings card is clicked."""
    if not callback_context.triggered:
        raise PreventUpdate

    triggered_value = callback_context.triggered[0].get("value")
    if not triggered_value:
        raise PreventUpdate

    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        raise PreventUpdate

    card_id = triggered.get("card_id")
    if not card_id:
        raise PreventUpdate

    if card_id == "runtime":
        return "/app/settings/runtime"

    if card_id == "graph-styling":
        return "/app/settings/graph-styling"

    raise PreventUpdate