"""Callbacks for the Connectors pages."""

from __future__ import annotations

import os
from datetime import datetime
import time
from typing import Any, Dict, List

import requests
import dash_bootstrap_components as dbc
from dash import ALL, MATCH, Input, Output, State, callback, callback_context, clientside_callback, html, no_update
from dash.exceptions import PreventUpdate

from app.common.timezone import humanize_duration, to_app_timezone
from app.runtime_settings import runtime_settings
from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.dash_app.components.common import create_alert
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
from .components.scan_status import render_scan_item


TIMEOUT_SECONDS = runtime_settings.get_int("HTTP_REQUEST_TIMEOUT")

# Fields that should be parsed from comma-separated strings to lists
ARRAY_FIELDS = {'include_spaces', 'exclude_spaces', 'branch_name_patterns', 'extraction_sources'}


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
                create_alert(message, color="danger", class_name="mb-0"),
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
    sections: Dict[str, List[Any]] = {"connections": [], "mcp": []}

    for connector_type, meta in CONNECTOR_REGISTRY.items():
        section_key = meta.get("section", "connections")
        if section_key not in sections:
            sections[section_key] = []
        data = by_type.get(connector_type, {})
        display_name = data.get("display_name", meta.get("display_name", connector_type))
        status = data.get("status", "not_configured")
        icon = meta.get("icon", "fa-solid fa-plug")
        sections[section_key].append(
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

    section_configs = [
        ("connections", "Connections"),
        ("mcp", "MCP Connectors"),
    ]
    result: List[Any] = []
    for section_key, section_label in section_configs:
        cards = sections.get(section_key, [])
        if not cards:
            continue
        result.append(
            dbc.Col(
                [
                    html.Div(
                        section_label,
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "fontWeight": FONT_WEIGHT_MEDIUM,
                            "color": COLOR_CHARCOAL_MEDIUM,
                            "textTransform": "uppercase",
                            "letterSpacing": "0.8px",
                            "marginBottom": SPACING_XSMALL,
                            "paddingBottom": SPACING_XSMALL,
                            "borderBottom": f"1px solid {COLOR_BORDER}",
                        },
                    ),
                    dbc.Row(cards, className="g-3"),
                ],
                width=12,
                style={"marginBottom": SPACING_SMALL},
            )
        )

    return result


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
    supports_items = CONNECTOR_REGISTRY.get(connector_type, {}).get("supports_items", True)
    try:
        detail_resp = requests.get(
            f"{api_base}/api/v1/connectors/{connector_type}", timeout=TIMEOUT_SECONDS
        )
        detail_resp.raise_for_status()
        if supports_items:
            items_resp = requests.get(
                f"{api_base}/api/v1/connectors/{connector_type}/configs", timeout=TIMEOUT_SECONDS
            )
            items_resp.raise_for_status()
            items_data = items_resp.json()
        else:
            items_data = []
        return (
            {"status": "ok", "connector_type": connector_type, "data": detail_resp.json()},
            {"status": "ok", "connector_type": connector_type, "items": items_data},
            None,
            None,
        )
    except requests.exceptions.RequestException as exc:
        error = {"status": "error", "connector_type": connector_type, "message": str(exc)}
        return error, error, None, None


@callback(
    Output("add-item-collapse", "is_open"),
    Input("add-item-collapse-toggle", "n_clicks"),
    State("add-item-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_add_item_collapse(n_clicks: int | None, is_open: bool) -> bool:
    """Toggle the Add New Repository collapsible section."""
    if not n_clicks:
        raise PreventUpdate
    return not is_open


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
    Output({"type": "connector-search-filters-store", "connector_type": MATCH}, "data"),
    Input("connector-edit-item", "data"),
    State({"type": "connector-search-filters-store", "connector_type": MATCH}, "id"),
)
def populate_search_filters_store(
    edit_state: Dict[str, Any] | None,
    store_id: Dict[str, Any],
):
    connector_type = store_id.get("connector_type")
    if connector_type != "github":
        return no_update

    if not edit_state:
        return {}

    state_connector_type = edit_state.get("connector_type")
    if state_connector_type != connector_type:
        return no_update

    if edit_state.get("item_id"):
        item = edit_state.get("item", {})
        raw_filters = item.get("search_filters")
        if not isinstance(raw_filters, dict):
            return {}
        return {str(k): str(v) for k, v in raw_filters.items()}

    if edit_state.get("action") == "clear":
        return {}

    return no_update


@callback(
    [
        Output({"type": "connector-search-filters-store", "connector_type": MATCH}, "data", allow_duplicate=True),
        Output({"type": "connector-search-filter-key", "connector_type": MATCH}, "value"),
        Output({"type": "connector-search-filter-value", "connector_type": MATCH}, "value"),
    ],
    [
        Input({"type": "connector-search-filter-add", "connector_type": MATCH}, "n_clicks"),
        Input({"type": "connector-search-filter-remove", "connector_type": MATCH, "filter_key": ALL}, "n_clicks"),
    ],
    [
        State({"type": "connector-search-filter-key", "connector_type": MATCH}, "value"),
        State({"type": "connector-search-filter-value", "connector_type": MATCH}, "value"),
        State({"type": "connector-search-filters-store", "connector_type": MATCH}, "data"),
    ],
    prevent_initial_call=True,
)
def update_search_filters_store(
    _add_clicks: int | None,
    _remove_clicks: List[int | None],
    key_value: str | None,
    value_value: str | None,
    store_data: Dict[str, str] | None,
):
    if not callback_context.triggered:
        return no_update, no_update, no_update

    triggered_value = callback_context.triggered[0].get("value")
    triggered = callback_context.triggered_id
    filters = dict(store_data or {})

    if isinstance(triggered, dict) and triggered.get("type") == "connector-search-filter-add":
        if not triggered_value:
            return no_update, no_update, no_update
        normalized_key = (key_value or "").strip()
        normalized_value = (value_value or "").strip()
        if not normalized_key or not normalized_value:
            return no_update, no_update, no_update
        filters[normalized_key] = normalized_value
        return filters, "", ""

    if isinstance(triggered, dict) and triggered.get("type") == "connector-search-filter-remove":
        if not triggered_value:
            return no_update, no_update, no_update
        remove_key = triggered.get("filter_key")
        if remove_key:
            filters.pop(remove_key, None)
        return filters, no_update, no_update

    return no_update, no_update, no_update


@callback(
    Output({"type": "connector-search-filter-list", "connector_type": MATCH}, "children"),
    Input({"type": "connector-search-filters-store", "connector_type": MATCH}, "data"),
    State({"type": "connector-search-filter-list", "connector_type": MATCH}, "id"),
)
def render_search_filters_list(
    store_data: Dict[str, str] | None,
    list_component_id: Dict[str, Any],
):
    filters = store_data or {}
    if not filters:
        return html.Div(
            "No search filters configured.",
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_SMALL,
                "color": COLOR_GRAY_MEDIUM,
            },
        )

    connector_type = list_component_id.get("connector_type", "github")

    rows: List[Any] = []
    for key, value in filters.items():
        rows.append(
            html.Div(
                [
                    html.Span(
                        f"{key}: {value}",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_CHARCOAL_MEDIUM,
                        },
                    ),
                    dbc.Button(
                        "Remove",
                        id={
                            "type": "connector-search-filter-remove",
                            "connector_type": connector_type,
                            "filter_key": key,
                        },
                        color="link",
                        size="sm",
                        className="p-0",
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "padding": f"{SPACING_XXXSMALL} 0",
                    "borderBottom": f"1px solid {COLOR_BORDER}",
                },
            )
        )
    return rows


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
        return [create_alert(store.get("message", "Failed to load items."), color="danger", class_name="mb-0")]

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
                
                # Convert to the configured app timezone and format
                local_dt = to_app_timezone(dt)
                fmt = runtime_settings.get("UI_DATETIME_FORMAT")
                actual_time = local_dt.strftime(fmt)
                duration_str = humanize_duration(local_dt)
                display_time_component = html.Span(duration_str, title=actual_time)
                header_text = [f"{label}: last configured at ", display_time_component]
            except (ValueError, TypeError, AttributeError):
                # Fallback to basic string parsing if datetime parsing fails
                if isinstance(updated_at, str) and "T" in updated_at:
                    display_time = updated_at.replace("T", " ").split(".")[0]
                    header_text = f"{label}: last configured at {display_time}"
                else:
                    header_text = f"{label}: last configured at {updated_at}"

        is_active = item.get("enabled", True)

        # Build 2-column grid from spec field order
        spec_fields = item_spec.get("fields", [])
        grid_rows = []
        for i in range(0, len(spec_fields), 2):
            left_spec = spec_fields[i]
            right_spec = spec_fields[i + 1] if i + 1 < len(spec_fields) else None

            # Left cell
            left_key = left_spec["key"]
            if left_key.endswith("token") or left_key.endswith("password"):
                left_cell = html.Div()
            else:
                left_value = _format_display_value(item.get(left_key))
                left_label = left_spec.get("label", left_key.replace("_", " ").title())
                left_cell = html.Div(
                    [
                        html.Span(
                            f"{left_label}: ",
                            style={
                                "fontFamily": FONT_SANS,
                                "fontSize": FONT_SIZE_SMALL,
                                "color": COLOR_GRAY_MEDIUM,
                            },
                        ),
                        html.Span(
                            left_value,
                            style={
                                "fontFamily": FONT_SANS,
                                "fontSize": FONT_SIZE_SMALL,
                                "color": COLOR_CHARCOAL_MEDIUM,
                            },
                        ),
                    ]
                )

            # Right cell
            if right_spec:
                right_key = right_spec["key"]
                if right_key.endswith("token") or right_key.endswith("password"):
                    right_cell = html.Div()
                else:
                    right_value = _format_display_value(item.get(right_key))
                    right_label = right_spec.get("label", right_key.replace("_", " ").title())
                    right_cell = html.Div(
                        [
                            html.Span(
                                f"{right_label}: ",
                                style={
                                    "fontFamily": FONT_SANS,
                                    "fontSize": FONT_SIZE_SMALL,
                                    "color": COLOR_GRAY_MEDIUM,
                                },
                            ),
                            html.Span(
                                right_value,
                                style={
                                    "fontFamily": FONT_SANS,
                                    "fontSize": FONT_SIZE_SMALL,
                                    "color": COLOR_CHARCOAL_MEDIUM,
                                },
                            ),
                        ]
                    )
            else:
                right_cell = html.Div()

            grid_rows.append(
                dbc.Row(
                    [
                        dbc.Col(left_cell, md=6, xs=12),
                        dbc.Col(right_cell, md=6, xs=12),
                    ],
                    className="g-3",
                    style={"marginBottom": SPACING_XXXSMALL},
                )
            )

        # Search filters row — right column only
        search_filters = item.get("search_filters")
        if search_filters and isinstance(search_filters, dict) and search_filters:
            filter_text = ", ".join([f"{k}: {v}" for k, v in search_filters.items()])
            grid_rows.append(
                dbc.Row(
                    [
                        dbc.Col(html.Div(), md=6, xs=12),
                        dbc.Col(
                            html.Div(
                                [
                                    html.Span(
                                        "Search Filters: ",
                                        style={
                                            "fontFamily": FONT_SANS,
                                            "fontSize": FONT_SIZE_SMALL,
                                            "color": COLOR_GRAY_MEDIUM,
                                        },
                                    ),
                                    html.Span(
                                        filter_text,
                                        style={
                                            "fontFamily": FONT_SANS,
                                            "fontSize": FONT_SIZE_SMALL,
                                            "color": COLOR_CHARCOAL_MEDIUM,
                                        },
                                    ),
                                ]
                            ),
                            md=6,
                            xs=12,
                        ),
                    ],
                    className="g-3",
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
                    html.Div(grid_rows),
                    html.Div(
                        [
                            dbc.Button(
                                "Test Connection",
                                id={"type": "connector-item-test", "connector_type": connector_type, "item_id": item_id},
                                size="sm",
                                color="secondary",
                                className="me-2",
                            ),
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
                                color="outline-danger",
                            ),
                            html.Div(
                                dbc.Switch(
                                    id={"type": "config-enabled-switch", "connector_type": connector_type, "config_id": item_id},
                                    value=is_active,
                                    label="Active" if is_active else "Disabled",
                                    className="executive-switch mb-0",
                                ),
                                style={"display": "flex", "alignItems": "center", "marginLeft": "auto"}
                            )
                        ],
                        style={"marginTop": SPACING_XSMALL, "display": "flex", "alignItems": "center"},
                    ),
                ],
                style={
                    "padding": SPACING_SMALL,
                    "border": f"1px solid {COLOR_BORDER}",
                    "borderRadius": "2px",
                    "backgroundColor": COLOR_BACKGROUND_LIGHT,
                    "marginBottom": SPACING_SMALL,
                    "opacity": "0.45" if not is_active else "1",
                },
            )
        )

    return cards


@callback(
    [
        Output("connector-edit-item", "data", allow_duplicate=True),
        Output("add-item-collapse", "is_open", allow_duplicate=True),
    ],
    Input({"type": "connector-item-edit", "connector_type": ALL, "item_id": ALL}, "n_clicks"),
    State({"type": "connector-item-edit", "connector_type": ALL, "item_id": ALL}, "id"),
    State("connector-items-store", "data"),
    prevent_initial_call=True,
)
def handle_item_edit(_clicks: List[int | None], ids: List[Dict[str, Any]], store: Dict[str, Any] | None):
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update

    if not callback_context.triggered or not callback_context.triggered[0].get("value"):
        return no_update, no_update

    connector_type = triggered.get("connector_type")
    item_id = triggered.get("item_id")
    if not store or store.get("status") != "ok":
        return no_update, no_update
    items = store.get("items", [])
    for item in items:
        if item.get("id") == item_id:
            return {"connector_type": connector_type, "item_id": item_id, "item": item}, True
    return no_update, no_update


@callback(
    [
        Output("connector-items-store", "data", allow_duplicate=True),
        Output("connector-edit-item", "data", allow_duplicate=True),
        Output("connector-action-feedback", "children", allow_duplicate=True),
        Output("add-item-collapse", "is_open", allow_duplicate=True),
    ],
    Input({"type": "connector-item-add", "connector_type": ALL}, "n_clicks"),
    State({"type": "connector-item-add", "connector_type": ALL}, "id"),
    State({"type": "connector-field", "connector_type": ALL, "section": "item", "field": ALL}, "id"),
    State({"type": "connector-field", "connector_type": ALL, "section": "item", "field": ALL}, "value"),
    State("connector-edit-item", "data"),
    State({"type": "connector-search-filters-store", "connector_type": ALL}, "id"),
    State({"type": "connector-search-filters-store", "connector_type": ALL}, "data"),
    prevent_initial_call=True,
)
def handle_item_save(
    _clicks: List[int | None],
    button_ids: List[Dict[str, Any]],
    field_ids: List[Dict[str, Any]],
    field_values: List[Any],
    edit_state: Dict[str, Any] | None,
    search_filter_store_ids: List[Dict[str, Any]],
    search_filter_store_data: List[Dict[str, str] | None],
):
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update, no_update, no_update

    connector_type = triggered.get("connector_type")
    if not connector_type:
        return no_update, no_update, no_update, no_update

    is_update = bool(edit_state and edit_state.get("item_id") and edit_state.get("connector_type") == connector_type)
    payload = _build_payload(connector_type, "item", field_ids, field_values, skip_empty_secrets=is_update)
    if connector_type == "github":
        search_filters = _get_search_filters_payload(
            connector_type,
            search_filter_store_ids,
            search_filter_store_data,
        )
        payload["search_filters"] = search_filters if search_filters else None
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
            create_alert("Item saved successfully.", color="success", class_name="mb-0"),
            False,
        )
    except requests.exceptions.RequestException as exc:
        return (
            no_update,
            no_update,
            create_alert(f"Failed to save item: {exc}", color="danger", class_name="mb-0"),
            no_update,
        )


@callback(
    Output("connector-item-delete-confirm", "displayed"),
    Output("connector-item-delete-target", "data"),
    Input({"type": "connector-item-delete", "connector_type": ALL, "item_id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def confirm_item_delete(_clicks: List[int | None]):
    """Show confirmation dialog before deleting an item."""
    if not any(n for n in _clicks if n):
        raise PreventUpdate
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        raise PreventUpdate
    return True, {"connector_type": triggered.get("connector_type"), "item_id": triggered.get("item_id")}


@callback(
    [
        Output("connector-items-store", "data", allow_duplicate=True),
        Output("connector-edit-item", "data", allow_duplicate=True),
        Output("connector-action-feedback", "children", allow_duplicate=True),
        Output("connector-item-delete-confirm", "displayed", allow_duplicate=True),
    ],
    Input("connector-item-delete-confirm", "submit_n_clicks"),
    State("connector-item-delete-target", "data"),
    prevent_initial_call=True,
)
def handle_item_delete(
    submit_clicks: int | None,
    target: Dict[str, Any] | None,
):
    if not submit_clicks:
        raise PreventUpdate

    if not target:
        return no_update, no_update, no_update, False

    connector_type = target.get("connector_type")
    item_id = target.get("item_id")

    if connector_type is None or item_id is None:
        return no_update, no_update, no_update, False

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
            create_alert("Item deleted.", color="success", class_name="mb-0"),
            False,
        )
    except requests.exceptions.RequestException as exc:
        return (
            no_update,
            no_update,
            create_alert(f"Failed to delete item: {exc}", color="danger", class_name="mb-0"),
            False,
        )


@callback(
    [
        Output("connector-edit-item", "data", allow_duplicate=True),
        Output("add-item-collapse", "is_open", allow_duplicate=True),
    ],
    Input({"type": "connector-item-cancel", "connector_type": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_item_cancel(_clicks: List[int | None]):
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update
    
    if not callback_context.triggered or not callback_context.triggered[0].get("value"):
        return no_update, no_update

    connector_type = triggered.get("connector_type")
    return {"connector_type": connector_type, "action": "clear", "timestamp": time.time()}, False


@callback(
    Output("connector-action-feedback", "children", allow_duplicate=True),
    Output("connector-scans-poll", "disabled", allow_duplicate=True),
    Input({"type": "connector-item-test", "connector_type": ALL, "item_id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_item_test_connection(_clicks: List[int | None]):
    """Test connection for a specific config item via the commands API.

    Sends a ``command_type: "test"`` command to the producer daemon, which
    runs the actual connectivity check and reports the result in the
    Recent Actions section.
    """
    if not callback_context.triggered:
        return no_update, no_update
    triggered_value = callback_context.triggered[0].get("value")
    if not triggered_value:
        return no_update, no_update
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update

    connector_type = triggered.get("connector_type")
    item_id = triggered.get("item_id")
    if not connector_type or item_id is None:
        return no_update, no_update

    container_name = CONNECTOR_REGISTRY.get(connector_type, {}).get("producer_container")
    if not container_name:
        return (
            create_alert(
                f"No producer container for {connector_type}.",
                color="warning",
                class_name="mb-0",
            ),
            no_update,
        )

    api_base = _get_api_base_url()
    try:
        response = requests.post(
            f"{api_base}/api/v1/commands/",
            json={
                "command_type": "test",
                "target": container_name,
                "parameters": {"item_id": item_id},
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        command_id = data.get("command_id", "unknown")

        return (
            create_alert(
                "Test triggered — check Recent Actions for the result.",
                color="info",
                class_name="mb-0",
            ),
            False,  # enable polling so result appears
        )
    except requests.exceptions.RequestException as exc:
        return (
            create_alert(
                f"Test failed: {exc}",
                color="danger",
                class_name="mb-0",
            ),
            no_update,
        )


@callback(
    Output("connector-action-feedback", "children", allow_duplicate=True),
    Input({"type": "connector-mcp-test", "connector_type": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_mcp_test_connection(_clicks: List[int | None]):
    """Test an MCP connector's connection via the synchronous /test endpoint.

    Unlike the producer connectors, MCP connectors run their client inside the
    app container, so the result is returned synchronously and rendered directly
    in the feedback area — no RabbitMQ command or polling is involved.
    """
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

    api_base = _get_api_base_url()
    try:
        response = requests.post(
            f"{api_base}/api/v1/connectors/{connector_type}/test",
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("message", "Connection test completed.")
        color = "success" if data.get("success") else "danger"
        return create_alert(message, color=color, class_name="mb-0")
    except requests.exceptions.RequestException as exc:
        return create_alert(
            f"Test failed: {exc}",
            color="danger",
            class_name="mb-0",
        )


@callback(
    Output("connector-action-feedback", "children", allow_duplicate=True),
    Output("connector-scans-poll", "disabled", allow_duplicate=True),
    Input({"type": "connector-cancel-scan", "command_id": ALL}, "n_clicks"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def handle_cancel_scan(n_clicks: List[int | None], pathname: str | None):
    """Cancel a running scan by sending a cancel command via the API."""
    if not callback_context.triggered:
        return no_update, no_update
    triggered_value = callback_context.triggered[0].get("value")
    if not triggered_value:
        return no_update, no_update
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update

    scan_command_id = triggered.get("command_id")
    if not scan_command_id:
        return no_update, no_update

    # Resolve container name from URL pathname
    if not pathname:
        return no_update, no_update
    connector_type = pathname.split("/app/connectors/")[-1]
    if not connector_type or connector_type not in CONNECTOR_REGISTRY:
        return no_update, no_update
    container_name = CONNECTOR_REGISTRY[connector_type].get("producer_container")
    if not container_name:
        return (
            create_alert(
                f"No producer container for {connector_type}.",
                color="warning",
                class_name="mb-0",
            ),
            no_update,
        )

    api_base = _get_api_base_url()
    try:
        response = requests.post(
            f"{api_base}/api/v1/commands/",
            json={
                "command_type": "cancel",
                "target": container_name,
                "parameters": {"cancel_command_id": scan_command_id},
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return (
            create_alert(
                f"Cancel sent for scan {scan_command_id[:8]}...",
                color="warning",
                class_name="mb-0",
            ),
            False,  # re-enable polling to see status transition
        )
    except requests.exceptions.RequestException as exc:
        return (
            create_alert(
                f"Failed to cancel scan: {exc}",
                color="danger",
                class_name="mb-0",
            ),
            no_update,
        )


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
            create_alert("Configuration saved.", color="success", class_name="mb-0"),
        )
    except requests.exceptions.RequestException as exc:
        return (
            no_update,
            create_alert(f"Failed to save configuration: {exc}", color="danger", class_name="mb-0"),
        )


@callback(
    Output("connector-delete-confirm", "displayed"),
    Output("connector-delete-target", "data"),
    Input({"type": "connector-delete", "connector_type": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def confirm_connector_delete(_clicks: List[int | None]):
    """Show confirmation dialog before deleting all configs for a connector."""
    if not any(n for n in _clicks if n):
        raise PreventUpdate
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        raise PreventUpdate
    return True, {"connector_type": triggered.get("connector_type")}


@callback(
    [
        Output("connector-detail-store", "data", allow_duplicate=True),
        Output("connector-items-store", "data", allow_duplicate=True),
        Output("connector-action-feedback", "children", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("connector-delete-confirm", "displayed", allow_duplicate=True),
    ],
    Input("connector-delete-confirm", "submit_n_clicks"),
    State("connector-delete-target", "data"),
    prevent_initial_call=True,
)
def handle_connector_delete(
    submit_clicks: int | None,
    target: Dict[str, Any] | None,
):
    if not submit_clicks:
        raise PreventUpdate

    if not target:
        return no_update, no_update, no_update, no_update, False

    connector_type = target.get("connector_type")

    if connector_type is None:
        return no_update, no_update, no_update, no_update, False

    api_base = _get_api_base_url()
    try:
        response = requests.delete(
            f"{api_base}/api/v1/connectors/{connector_type}", timeout=TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return (
            {"status": "ok", "connector_type": connector_type, "data": {"config": None}},
            {"status": "ok", "connector_type": connector_type, "items": []},
            create_alert("Configuration deleted.", color="success", class_name="mb-0"),
            "/app/connectors",
            False,
        )
    except requests.exceptions.RequestException as exc:
        return (
            no_update,
            no_update,
            create_alert(f"Delete failed: {exc}", color="danger", class_name="mb-0"),
            no_update,
            False,
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
    key = spec.get("key")
    if key in ARRAY_FIELDS:
        if value is None or str(value).strip() == "":
            return []
        if isinstance(value, list):
            return value
        return [s.strip() for s in str(value).split(",") if s.strip()]

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
    if key in ARRAY_FIELDS and isinstance(value, list):
        return ", ".join(value)

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
    
    if connector_type:
        spec_fields = _get_spec_fields(connector_type, section)
        for spec in spec_fields:
            if spec.get("key") == key and "default" in spec:
                return _normalize_field_value(connector_type, section, key, spec["default"])
                
    return _normalize_field_value(connector_type, section, key, None)


def _format_display_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, dict):
        return ", ".join([f"{k}: {v}" for k, v in value.items()]) if value else "—"
    if isinstance(value, list):
        return ", ".join([str(v) for v in value]) if value else "—"
    return str(value)


def _get_search_filters_payload(
    connector_type: str,
    store_ids: List[Dict[str, Any]],
    store_data: List[Dict[str, str] | None],
) -> Dict[str, str]:
    for store_id, data in zip(store_ids, store_data):
        if store_id.get("connector_type") != connector_type:
            continue
        if not isinstance(data, dict):
            return {}
        normalized: Dict[str, str] = {}
        for key, value in data.items():
            normalized_key = str(key).strip()
            normalized_value = str(value).strip()
            if not normalized_key or not normalized_value:
                continue
            normalized[normalized_key] = normalized_value
        return normalized
    return {}


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


@callback(
    [
        Output("connector-action-feedback", "children", allow_duplicate=True),
        Output({"type": "config-enabled-switch", "connector_type": MATCH, "config_id": MATCH}, "value"),
        Output({"type": "config-enabled-switch", "connector_type": MATCH, "config_id": MATCH}, "label"),
        Output("connector-items-store", "data", allow_duplicate=True),
    ],
    Input({"type": "config-enabled-switch", "connector_type": MATCH, "config_id": MATCH}, "value"),
    State("connector-items-store", "data"),
    prevent_initial_call=True
)
def handle_inline_toggle(new_enabled_state: bool, store: Dict[str, Any] | None):
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update, no_update
        
    triggered_id = ctx.triggered_id
    if not isinstance(triggered_id, dict):
        return no_update, no_update, no_update, no_update

    connector_type = triggered_id.get("connector_type")
    config_id = triggered_id.get("config_id")
    
    if not store or store.get("status") != "ok":
        return no_update, not new_enabled_state, "Active" if not new_enabled_state else "Disabled", no_update
        
    api_base = _get_api_base_url()
    try:
        # Dedicated status endpoint for a clean atomic update, avoiding full payload PUT
        response = requests.patch(
            f"{api_base}/api/v1/connectors/{connector_type}/configs/{config_id}/status",
            json={"enabled": new_enabled_state},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        
        # Update local store efficiently to keep UI in sync
        updated_store = dict(store)
        for i, item in enumerate(updated_store.get("items", [])):
            if item.get("id") == config_id:
                updated_store["items"][i]["enabled"] = new_enabled_state
                break
                
        return no_update, no_update, "Active" if new_enabled_state else "Disabled", updated_store
        
    except requests.exceptions.RequestException as exc:
        error_alert = create_alert(f"Failed to update configuration: {str(exc)}", color="danger", class_name="mb-0")
        return error_alert, not new_enabled_state, "Active" if not new_enabled_state else "Disabled", no_update


# ═══════════════════════════════════════════════════════════════════════════
#  Scan callbacks
# ═══════════════════════════════════════════════════════════════════════════


@callback(
    Output("connector-action-feedback", "children", allow_duplicate=True),
    Output("connector-scans-poll", "disabled", allow_duplicate=True),
    Output("connector-scans-list", "children", allow_duplicate=True),
    Input({"type": "connector-run-scan", "connector_type": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_run_scan(n_clicks: List[int | None]):
    """Send a scan command via the API when the "Run Scan" button is clicked.

    Also enables the scan-polling interval so the scan list auto-refreshes,
    and immediately loads the updated scan list so the new row appears
    without waiting for the first poll tick.
    """
    _ = n_clicks  # used by Dash as trigger
    if not callback_context.triggered:
        return no_update, no_update, no_update
    triggered_value = callback_context.triggered[0].get("value")
    if not triggered_value:
        return no_update, no_update, no_update
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update, no_update
    connector_type = triggered.get("connector_type")
    if not connector_type or connector_type not in CONNECTOR_REGISTRY:
        return no_update, no_update, no_update

    container_name = CONNECTOR_REGISTRY[connector_type].get("producer_container")
    if not container_name:
        return create_alert(
            f"No producer container configured for {connector_type}.",
            color="warning",
            class_name="mb-0",
        ), no_update, no_update

    api_base = _get_api_base_url()
    try:
        response = requests.post(
            f"{api_base}/api/v1/commands/",
            json={
                "command_type": "scan",
                "target": container_name,
                "parameters": {},
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        command_id = data.get("command_id", "unknown")

        # Immediately fetch the updated scan list so the new row appears
        # without waiting for the next poll interval.
        scans_response = requests.get(
            f"{api_base}/api/v1/commands/",
            params={"target": container_name, "limit": runtime_settings.get_int("RECENT_ACTIONS_LIMIT")},
            timeout=TIMEOUT_SECONDS,
        )
        scans_response.raise_for_status()
        scans_data = scans_response.json()
        commands = scans_data.get("commands", [])
        if commands:
            scans_children = html.Div([render_scan_item(cmd) for cmd in commands])
        else:
            scans_children = html.Div(
                "No recent actions.",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_SMALL,
                    "color": COLOR_GRAY_MEDIUM,
                },
            )

        return (
            create_alert(
                f"Scan triggered! Command ID: {command_id}",
                color="success",
                class_name="mb-0",
            ),
            False,  # enable the polling interval
            scans_children,
        )
    except requests.exceptions.RequestException as exc:
        return (
            create_alert(
                f"Failed to trigger scan: {exc}",
                color="danger",
                class_name="mb-0",
            ),
            no_update,
            no_update,
        )


@callback(
    Output("connector-scans-list", "children"),
    [Input("connector-scans-poll", "n_intervals"),
     Input("url", "pathname")],
)
def load_recent_scans(
    n_intervals: int | None,
    pathname: str | None,
):
    """Load recent scan commands for this connector.

    Polled every 5 seconds while scans are in progress.  Disabled when idle.
    """
    _ = n_intervals  # used by Dash as trigger
    if not pathname or not pathname.startswith("/app/connectors/"):
        return no_update

    connector_type = pathname.split("/app/connectors/")[-1]
    if not connector_type or connector_type not in CONNECTOR_REGISTRY:
        return no_update

    container_name = CONNECTOR_REGISTRY[connector_type].get("producer_container")
    if not container_name:
        return no_update

    api_base = _get_api_base_url()
    try:
        response = requests.get(
            f"{api_base}/api/v1/commands/",
            params={"target": container_name, "limit": runtime_settings.get_int("RECENT_ACTIONS_LIMIT")},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        commands = data.get("commands", [])
        if not commands:
            return html.Div(
                "No recent actions.",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_SMALL,
                    "color": COLOR_GRAY_MEDIUM,
                },
            )
        items = [render_scan_item(cmd) for cmd in commands]
        return html.Div(items)
    except requests.exceptions.RequestException:
        # Silently fail on poll — don't spam UI with errors every 5s
        return no_update


clientside_callback(
    """
    function(scans_children) {
        // Recursively search for active scan status text in the serialized
        // Dash component tree.  Returns true (disable poll) when no scans
        // are in progress, false (keep polling) when any are still active.
        if (!scans_children) {
            return true;
        }

        var activeStatuses = ['Running', 'Queued', 'Accepted'];

        function walk(node) {
            if (typeof node === 'string') {
                for (var i = 0; i < activeStatuses.length; i++) {
                    if (node.indexOf(activeStatuses[i]) !== -1) {
                        return true;
                    }
                }
                return false;
            }
            if (node && node.props && node.props.children) {
                var children = node.props.children;
                if (!Array.isArray(children)) {
                    children = [children];
                }
                for (var j = 0; j < children.length; j++) {
                    if (walk(children[j])) {
                        return true;
                    }
                }
            }
            return false;
        }

        // scans_children is the children of connector-scans-list.
        // If it's an array, check each top-level item; otherwise check the single node.
        var items = Array.isArray(scans_children) ? scans_children : [scans_children];
        for (var k = 0; k < items.length; k++) {
            if (walk(items[k])) {
                return false;  // active scan found — keep polling
            }
        }
        return true;  // no active scans — stop polling
    }
    """,
    Output("connector-scans-poll", "disabled"),
    Input("connector-scans-list", "children"),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(edit_data) {
        if (edit_data && edit_data.item_id) {
            setTimeout(function() {
                var el = document.getElementById('add-item-collapse-toggle');
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 200);
        }
        return '';
    }
    """,
    Output("connector-scroll-trigger", "data"),
    Input("connector-edit-item", "data"),
    prevent_initial_call=True,
)


clientside_callback(
    """
    function(feedback_children) {
        if (feedback_children) {
            setTimeout(function() {
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }, 100);
        }
        return '';
    }
    """,
    Output("connector-scroll-trigger", "data"),
    Input("connector-action-feedback", "children"),
    prevent_initial_call=True,
)
