"""Callbacks for the Connectors pages."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import requests
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, callback, callback_context, html, no_update

from app.settings import settings
from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.dash_app.styles import COLOR_GRAY_MEDIUM, FONT_SANS, FONT_SIZE_SMALL
from .components.connector_card import connector_card

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT
def _get_api_base_url() -> str:
    return os.getenv("API_BASE_URL", "http://localhost:8000")


@callback(
    Output("connectors-store", "data"),
    Input("url", "pathname"),
)
def load_connectors(pathname: str):
    if pathname not in ("/app/connectors", "/app/connectors/"):
        return no_update

    api_base = _get_api_base_url()
    try:
        response = requests.get(f"{api_base}/api/v1/connectors/", timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return {"status": "ok", "data": response.json()}
    except requests.exceptions.RequestException as exc:
        return {"status": "error", "message": str(exc)}


@callback(
    Output("connectors-grid", "children"),
    Input("connectors-store", "data"),
)
def render_connectors(store: Dict[str, Any] | None):
    if not store:
        return [
            dbc.Col(
                html.Div(
                    "Loading connectors...",
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": FONT_SIZE_SMALL,
                        "color": COLOR_GRAY_MEDIUM,
                    },
                ),
                width=12,
            )
        ]

    if store.get("status") != "ok":
        message = store.get("message", "Failed to load connectors.")
        return [
            dbc.Col(
                dbc.Alert(message, color="danger", className="mb-0"),
                width=12,
            )
        ]

    connectors = store.get("data", [])
    if not connectors:
        return [
            dbc.Col(
                html.Div(
                    "No connectors available.",
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": FONT_SIZE_SMALL,
                        "color": COLOR_GRAY_MEDIUM,
                    },
                ),
                width=12,
            )
        ]

    by_type = {c.get("connector_type"): c for c in connectors}
    cards: List[Any] = []

    for connector_type, meta in CONNECTOR_REGISTRY.items():
        data = by_type.get(connector_type, {})
        display_name = data.get("display_name", meta.get("display_name", connector_type))
        status = data.get("status", "not_configured")
        icon = meta.get("icon", "fa-solid fa-plug")
        cards.append(
            dbc.Col(
                connector_card(
                    connector_type=connector_type,
                    display_name=display_name,
                    icon=icon,
                    status=status,
                ),
                md=3,
                sm=6,
                xs=12,
            )
        )

    return cards


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Input({"type": "connector-card", "connector_type": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_card_click(_n_clicks: List[int | None]):
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    connector_type = triggered.get("connector_type")
    if not connector_type:
        return no_update
    return f"/app/connectors/{connector_type}"
