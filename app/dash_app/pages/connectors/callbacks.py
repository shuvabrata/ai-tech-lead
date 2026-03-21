"""Callbacks for the Connectors pages."""

from __future__ import annotations

import os
from datetime import datetime
import time
from typing import Any, Dict, List

import requests
import dash_bootstrap_components as dbc
from dash import ALL, MATCH, Input, Output, State, callback, callback_context, html, no_update

from app.settings import settings
from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.dash_app.styles import (
    COLOR_BACKGROUND_LIGHT,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_MEDIUM,
    FONT_SANS,
    FONT_SIZE_SMALL,
    FONT_WEIGHT_MEDIUM,
    SPACING_XSMALL,
    SPACING_XXXSMALL,
    SPACING_SMALL,
)
from .components.connector_card import connector_card
from .components.config_forms import (
    CONFIG_FORM_SPECS,
    FIELD_CHECKBOX,
    FIELD_MULTISELECT,
    FIELD_NUMBER,
    FIELD_TEXTAREA,
)

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
    Input({"type": "connector-card", "connector_type": ALL}, "n_clicks_timestamp"),
    prevent_initial_call=True,
)
def handle_card_click(_timestamps: List[int | None]):
    if not callback_context.triggered:
        return no_update
    triggered_value = callback_context.triggered[0].get("value")
    if not triggered_value:
        return no_update
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    connector_type = triggered.get("connector_type")
    if not connector_type:
        return no_update
    return f"/app/connectors/{connector_type}"


@callback(
    [
        Output("connector-detail-store", "data"),
        Output("connector-items-store", "data"),
        Output("connector-edit-item", "data"),
        Output("connector-action-feedback", "children", allow_duplicate=True),
    ],
    Input("url", "pathname"),
    prevent_initial_call="initial_duplicate",
)
def load_connector_detail(pathname: str):
    if not pathname or not pathname.startswith("/app/connectors/"):
        return no_update, no_update, no_update, no_update

    connector_type = pathname.split("/app/connectors/")[-1]
    if not connector_type:
        return no_update, no_update, no_update, no_update

    if connector_type not in CONNECTOR_REGISTRY:
        error = {"status": "error", "connector_type": connector_type, "message": "Unknown connector type"}
        return error, error, None, None

    api_base = _get_api_base_url()
    try:
        detail_resp = requests.get(
            f"{api_base}/api/v1/connectors/{connector_type}", timeout=TIMEOUT_SECONDS
        )
        detail_resp.raise_for_status()
        items_resp = requests.get(
            f"{api_base}/api/v1/connectors/{connector_type}/configs", timeout=TIMEOUT_SECONDS
        )
        items_resp.raise_for_status()
        return (
            {"status": "ok", "connector_type": connector_type, "data": detail_resp.json()},
            {"status": "ok", "connector_type": connector_type, "items": items_resp.json()},
            None,
            None,
        )
    except requests.exceptions.RequestException as exc:
        error = {"status": "error", "connector_type": connector_type, "message": str(exc)}
        return error, error, None, None


@callback(
    Output({"type": "connector-field", "connector_type": ALL, "section": "connector", "field": ALL}, "value"),
    Input("connector-detail-store", "data"),
    State({"type": "connector-field", "connector_type": ALL, "section": "connector", "field": ALL}, "id"),
)
def populate_connector_fields(store: Dict[str, Any] | None, field_ids: List[Dict[str, Any]]):
    if not field_ids:
        return no_update
    if not store or store.get("status") != "ok":
        return [_default_field_value(field_id) for field_id in field_ids]

    config = store.get("data", {}).get("config") or {}
    connector_type = store.get("connector_type")
    values: List[Any] = []
    for field_id in field_ids:
        value = config.get(field_id["field"])
        values.append(_normalize_field_value(connector_type, "connector", field_id["field"], value))
    return values


@callback(
    Output({"type": "connector-field", "connector_type": ALL, "section": "item", "field": ALL}, "value"),
    Input("connector-edit-item", "data"),
    State({"type": "connector-field", "connector_type": ALL, "section": "item", "field": ALL}, "id"),
)
def populate_item_fields(edit_state: Dict[str, Any] | None, field_ids: List[Dict[str, Any]]):
    if not field_ids:
        return no_update

    if not edit_state or not edit_state.get("item_id"):
        return [_default_field_value(field_id) for field_id in field_ids]

    connector_type = edit_state.get("connector_type")
    item_data = edit_state.get("item", {})
    values: List[Any] = []
    for field_id in field_ids:
        key = field_id["field"]
        value = item_data.get(key)
        values.append(_normalize_field_value(connector_type, "item", key, value))
    return values


@callback(
    Output({"type": "connector-item-add", "connector_type": MATCH}, "children"),
    Input("connector-edit-item", "data"),
    State({"type": "connector-item-add", "connector_type": MATCH}, "id"),
)
def update_item_button_label(edit_state: Dict[str, Any] | None, button_id: Dict[str, Any]):
    if edit_state and edit_state.get("item_id") and edit_state.get("connector_type") == button_id.get("connector_type"):
        return "Update Item"
    return "Add Item"


@callback(
    Output("connector-items-list", "children"),
    Input("connector-items-store", "data"),
)
def render_items_list(store: Dict[str, Any] | None):
    if not store:
        return _empty_items_message("Loading items...")

    if store.get("status") != "ok":
        return [dbc.Alert(store.get("message", "Failed to load items."), color="danger", className="mb-0")]

    items = store.get("items", [])
    connector_type = store.get("connector_type")
    item_spec = CONFIG_FORM_SPECS.get(connector_type, {}).get("item", {})
    label = item_spec.get("label", "Item")

    if not items:
        return _empty_items_message("No items configured yet.")

    cards = []
    for item in items:
        item_id = item.get("id")
        updated_at = item.get("updated_at") or item.get("created_at")
        
        header_text = label
        if updated_at:
            try:
                if isinstance(updated_at, str):
                    # Replace 'Z' with '+00:00' for compatible ISO parsing in Python 3.10 and older
                    dt_str = updated_at.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(dt_str)
                else:
                    dt = updated_at
                
                # Convert to system local timezone and format
                local_dt = dt.astimezone()
                fmt = getattr(settings, "UI_DATETIME_FORMAT", "%b %d, %Y %I:%M %p")
                display_time = local_dt.strftime(fmt)
                header_text = f"{label}: last configured at {display_time}"
            except (ValueError, TypeError, AttributeError):
                # Fallback to basic string parsing if datetime parsing fails
                if isinstance(updated_at, str) and "T" in updated_at:
                    display_time = updated_at.replace("T", " ").split(".")[0]
                    header_text = f"{label}: last configured at {display_time}"
                else:
                    header_text = f"{label}: last configured at {updated_at}"

        fields = [k for k in item.keys() if k not in ("id", "connector_id", "created_at", "updated_at")]
        field_rows = []
        for key in fields:
            value = _format_display_value(item.get(key))
            field_rows.append(
                html.Div(
                    [
                        html.Span(
                            f"{key.replace('_', ' ').title()}: ",
                            style={
                                "fontFamily": FONT_SANS,
                                "fontSize": FONT_SIZE_SMALL,
                                "color": COLOR_GRAY_MEDIUM,
                            },
                        ),
                        html.Span(
                            value,
                            style={
                                "fontFamily": FONT_SANS,
                                "fontSize": FONT_SIZE_SMALL,
                                "color": COLOR_CHARCOAL_MEDIUM,
                            },
                        ),
                    ],
                    style={"marginBottom": SPACING_XXXSMALL},
                )
            )

        cards.append(
            html.Div(
                [
                    html.Div(
                        header_text,
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "fontWeight": FONT_WEIGHT_MEDIUM,
                            "color": COLOR_CHARCOAL_MEDIUM,
                            "marginBottom": SPACING_XSMALL,
                        },
                    ),
                    html.Div(field_rows),
                    html.Div(
                        [
                            dbc.Button(
                                "Edit",
                                id={"type": "connector-item-edit", "connector_type": connector_type, "item_id": item_id},
                                size="sm",
                                color="secondary",
                                className="me-2",
                            ),
                            dbc.Button(
                                "Delete",
                                id={"type": "connector-item-delete", "connector_type": connector_type, "item_id": item_id},
                                size="sm",
                                color="danger",
                            ),
                        ],
                        style={"marginTop": SPACING_XSMALL},
                    ),
                ],
                style={
                    "padding": SPACING_SMALL,
                    "border": f"1px solid {COLOR_BORDER}",
                    "borderRadius": "2px",
                    "backgroundColor": COLOR_BACKGROUND_LIGHT,
                    "marginBottom": SPACING_SMALL,
                },
            )
        )

    return cards


@callback(
    Output("connector-edit-item", "data", allow_duplicate=True),
    Input({"type": "connector-item-edit", "connector_type": ALL, "item_id": ALL}, "n_clicks"),
    State({"type": "connector-item-edit", "connector_type": ALL, "item_id": ALL}, "id"),
    State("connector-items-store", "data"),
    prevent_initial_call=True,
)
def handle_item_edit(_clicks: List[int | None], ids: List[Dict[str, Any]], store: Dict[str, Any] | None):
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update

    if not callback_context.triggered or not callback_context.triggered[0].get("value"):
        return no_update

    connector_type = triggered.get("connector_type")
    item_id = triggered.get("item_id")
    if not store or store.get("status") != "ok":
        return no_update
    items = store.get("items", [])
    for item in items:
        if item.get("id") == item_id:
            return {"connector_type": connector_type, "item_id": item_id, "item": item}
    return no_update


@callback(
    [
        Output("connector-items-store", "data", allow_duplicate=True),
        Output("connector-edit-item", "data", allow_duplicate=True),
        Output("connector-action-feedback", "children", allow_duplicate=True),
    ],
    Input({"type": "connector-item-add", "connector_type": ALL}, "n_clicks"),
    State({"type": "connector-item-add", "connector_type": ALL}, "id"),
    State({"type": "connector-field", "connector_type": ALL, "section": "item", "field": ALL}, "id"),
    State({"type": "connector-field", "connector_type": ALL, "section": "item", "field": ALL}, "value"),
    State("connector-edit-item", "data"),
    prevent_initial_call=True,
)
def handle_item_save(
    _clicks: List[int | None],
    button_ids: List[Dict[str, Any]],
    field_ids: List[Dict[str, Any]],
    field_values: List[Any],
    edit_state: Dict[str, Any] | None,
):
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update, no_update

    connector_type = triggered.get("connector_type")
    if not connector_type:
        return no_update, no_update, no_update

    is_update = bool(edit_state and edit_state.get("item_id") and edit_state.get("connector_type") == connector_type)
    payload = _build_payload(connector_type, "item", field_ids, field_values, skip_empty_secrets=is_update)
    api_base = _get_api_base_url()
    try:
        if is_update:
            item_id = edit_state.get("item_id")
            response = requests.put(
                f"{api_base}/api/v1/connectors/{connector_type}/configs/{item_id}",
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
        else:
            response = requests.post(
                f"{api_base}/api/v1/connectors/{connector_type}/configs",
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
        response.raise_for_status()

        items_resp = requests.get(
            f"{api_base}/api/v1/connectors/{connector_type}/configs", timeout=TIMEOUT_SECONDS
        )
        items_resp.raise_for_status()
        updated_store = {
            "status": "ok",
            "connector_type": connector_type,
            "items": items_resp.json(),
        }
        clear_state = {"connector_type": connector_type, "action": "clear", "timestamp": time.time()}
        return (
            updated_store,
            clear_state,
            dbc.Alert("Item saved successfully.", color="success", className="mt-2"),
        )
    except requests.exceptions.RequestException as exc:
        return (
            no_update,
            no_update,
            dbc.Alert(f"Failed to save item: {exc}", color="danger", className="mt-2"),
        )


@callback(
    [
        Output("connector-items-store", "data", allow_duplicate=True),
        Output("connector-edit-item", "data", allow_duplicate=True),
        Output("connector-action-feedback", "children", allow_duplicate=True),
    ],
    Input({"type": "connector-item-delete", "connector_type": ALL, "item_id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_item_delete(_clicks: List[int | None]):
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update, no_update

    connector_type = triggered.get("connector_type")
    item_id = triggered.get("item_id")
    # Find the n_clicks value for the triggered button
    n_clicks = None
    if _clicks and len(_clicks) > 0:
        # Try to match the triggered button
        try:
            idx = callback_context.inputs_list[0].index(triggered)
            n_clicks = _clicks[idx]
        except Exception:
            n_clicks = _clicks[0]
    # Only proceed if n_clicks > 0
    if not n_clicks or n_clicks < 1:
        return no_update, no_update, no_update

    api_base = _get_api_base_url()
    try:
        response = requests.delete(
            f"{api_base}/api/v1/connectors/{connector_type}/configs/{item_id}",
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        items_resp = requests.get(
            f"{api_base}/api/v1/connectors/{connector_type}/configs", timeout=TIMEOUT_SECONDS
        )
        items_resp.raise_for_status()
        updated_store = {
            "status": "ok",
            "connector_type": connector_type,
            "items": items_resp.json(),
        }
        clear_state = {"connector_type": connector_type, "action": "clear", "timestamp": time.time()}
        return (
            updated_store,
            clear_state,
            dbc.Alert("Item deleted.", color="success", className="mt-2"),
        )
    except requests.exceptions.RequestException as exc:
        return (
            no_update,
            no_update,
            dbc.Alert(f"Failed to delete item: {exc}", color="danger", className="mt-2"),
        )


@callback(
    Output("connector-edit-item", "data", allow_duplicate=True),
    Input({"type": "connector-item-cancel", "connector_type": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_item_cancel(_clicks: List[int | None]):
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    
    if not callback_context.triggered or not callback_context.triggered[0].get("value"):
        return no_update

    connector_type = triggered.get("connector_type")
    return {"connector_type": connector_type, "action": "clear", "timestamp": time.time()}


@callback(
    [
        Output("connector-detail-store", "data", allow_duplicate=True),
        Output("connector-action-feedback", "children", allow_duplicate=True),
    ],
    Input({"type": "connector-save", "connector_type": ALL}, "n_clicks"),
    State({"type": "connector-save", "connector_type": ALL}, "id"),
    State({"type": "connector-field", "connector_type": ALL, "section": "connector", "field": ALL}, "id"),
    State({"type": "connector-field", "connector_type": ALL, "section": "connector", "field": ALL}, "value"),
    prevent_initial_call=True,
)
def handle_connector_save(
    _clicks: List[int | None],
    button_ids: List[Dict[str, Any]],
    field_ids: List[Dict[str, Any]],
    field_values: List[Any],
):
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update
    connector_type = triggered.get("connector_type")
    payload_config = _build_payload(connector_type, "connector", field_ids, field_values)

    api_base = _get_api_base_url()
    try:
        response = requests.patch(
            f"{api_base}/api/v1/connectors/{connector_type}",
            json={"config": payload_config},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        updated = response.json()
        return (
            {"status": "ok", "connector_type": connector_type, "data": updated},
            dbc.Alert("Configuration saved.", color="success", className="mt-2"),
        )
    except requests.exceptions.RequestException as exc:
        return (
            no_update,
            dbc.Alert(f"Failed to save configuration: {exc}", color="danger", className="mt-2"),
        )


@callback(
    Output("connector-action-feedback", "children", allow_duplicate=True),
    Input({"type": "connector-test", "connector_type": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_connector_test(_clicks: List[int | None]):
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    connector_type = triggered.get("connector_type")
    api_base = _get_api_base_url()
    try:
        response = requests.post(
            f"{api_base}/api/v1/connectors/{connector_type}/test",
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("message", "Connection verified.")
        return dbc.Alert(message, color="success", className="mt-2")
    except requests.exceptions.RequestException as exc:
        return dbc.Alert(f"Test failed: {exc}", color="danger", className="mt-2")


@callback(
    [
        Output("connector-detail-store", "data", allow_duplicate=True),
        Output("connector-items-store", "data", allow_duplicate=True),
        Output("connector-action-feedback", "children", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
    ],
    Input({"type": "connector-delete", "connector_type": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_connector_delete(_clicks: List[int | None]):
    if not callback_context.triggered:
        return no_update, no_update, no_update, no_update
    triggered_value = callback_context.triggered[0].get("value")
    if not triggered_value:
        return no_update, no_update, no_update, no_update
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update, no_update, no_update
    connector_type = triggered.get("connector_type")
    api_base = _get_api_base_url()
    try:
        response = requests.delete(
            f"{api_base}/api/v1/connectors/{connector_type}", timeout=TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return (
            {"status": "ok", "connector_type": connector_type, "data": {"config": None}},
            {"status": "ok", "connector_type": connector_type, "items": []},
            dbc.Alert("Configuration deleted.", color="success", className="mt-2"),
            "/app/connectors",
        )
    except requests.exceptions.RequestException as exc:
        return (
            no_update,
            no_update,
            dbc.Alert(f"Delete failed: {exc}", color="danger", className="mt-2"),
            no_update,
        )


def _build_payload(
    connector_type: str,
    section: str,
    field_ids: List[Dict[str, Any]],
    field_values: List[Any],
    skip_empty_secrets: bool = False,
) -> Dict[str, Any]:
    spec_fields = _get_spec_fields(connector_type, section)
    field_map = {field["key"]: field for field in spec_fields}
    payload: Dict[str, Any] = {}
    for field_id, value in zip(field_ids, field_values):
        if field_id.get("connector_type") != connector_type or field_id.get("section") != section:
            continue
        key = field_id.get("field")
        spec = field_map.get(key, {})
        if skip_empty_secrets and spec.get("secret") and value in (None, ""):
            continue
        payload[key] = _coerce_field_value(spec, value)
    return payload


def _get_spec_fields(connector_type: str, section: str) -> List[Dict[str, Any]]:
    form_spec = CONFIG_FORM_SPECS.get(connector_type, {})
    if section == "connector":
        return form_spec.get("connector_config", [])
    return form_spec.get("item", {}).get("fields", [])


def _coerce_field_value(spec: Dict[str, Any], value: Any) -> Any:
    input_type = spec.get("input_type")
    if input_type == FIELD_TEXTAREA and spec.get("is_list"):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        lines = [line.strip() for line in str(value).splitlines()]
        return [line for line in lines if line]
    if input_type == FIELD_MULTISELECT:
        return value or []
    if input_type == FIELD_CHECKBOX:
        return bool(value)
    if input_type == FIELD_NUMBER:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


def _normalize_field_value(connector_type: str | None, section: str, key: str, value: Any) -> Any:
    if connector_type:
        spec_fields = _get_spec_fields(connector_type, section)
        for spec in spec_fields:
            if spec.get("key") == key:
                input_type = spec.get("input_type")
                if spec.get("secret") and value in ("********", None, ""):
                    return ""
                if input_type == FIELD_CHECKBOX:
                    return bool(value) if value is not None else False
                if input_type == FIELD_MULTISELECT:
                    return value or []
                if input_type == FIELD_TEXTAREA and spec.get("is_list"):
                    if value is None:
                        return ""
                    if isinstance(value, list):
                        return "\n".join(value)
                return value
    return value


def _default_field_value(field_id: Dict[str, Any]) -> Any:
    connector_type = field_id.get("connector_type")
    section = field_id.get("section")
    key = field_id.get("field")
    return _normalize_field_value(connector_type, section, key, None)


def _format_display_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join([str(v) for v in value]) if value else "—"
    return str(value)


def _empty_items_message(message: str) -> List[Any]:
    return [
        html.Div(
            message,
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_SMALL,
                "color": COLOR_GRAY_MEDIUM,
                "paddingTop": SPACING_XSMALL,
            },
        )
    ]
