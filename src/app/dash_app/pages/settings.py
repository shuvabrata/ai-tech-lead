"""Runtime Application Settings Editor.

Provides a functional UI for viewing and editing runtime-configurable settings
backed by the ``/api/v1/settings/`` REST API.

Data flow:
    1. Page loads → ``GET /api/v1/settings/`` → populate UI.
    2. User edits → "Save All" → ``PATCH /api/v1/settings/`` → refresh UI.
    3. User clicks "Reset" → ``POST /api/v1/settings/{key}/reset`` → refresh UI.
"""

from __future__ import annotations

import json
import os
from typing import Any

import dash_bootstrap_components as dbc
import requests
from dash import (
    ALL,
    MATCH,
    Input,
    Output,
    State,
    callback,
    callback_context,
    clientside_callback,
    dcc,
    html,
    no_update,
)
from dash.exceptions import PreventUpdate

from app.dash_app.components.common import create_alert
from app.dash_app.styles import (
    BUTTON_PRIMARY_STYLE,
    CARD_CONTAINER_STYLE,
    COLOR_BACKGROUND_LIGHT,
    COLOR_BACKGROUND_WHITE,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_ERROR,
    COLOR_GRAY_MEDIUM,
    COLOR_NAVY,
    COLOR_TEXT_MUTED,
    FONT_SANS,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_SIZE_XSMALL,
    FONT_SIZE_XTINY,
    FONT_WEIGHT_SEMIBOLD,
    INPUT_STYLE,
    PAGE_HEADER_STYLE,
    SPACING_XXSMALL,
    SPACING_XSMALL,
    SPACING_SMALL,
)

# ── Constants ──────────────────────────────────────────────────────────

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
SETTINGS_API = f"{API_BASE}/api/v1/settings/"

CATEGORY_META: dict[str, dict[str, str]] = {
    "network": {"label": "Network", "icon": "fa-solid fa-globe"},
    "graph": {"label": "Graph", "icon": "fa-solid fa-project-diagram"},
    "connectors": {"label": "Connectors", "icon": "fa-solid fa-plug"},
    "ui": {"label": "UI", "icon": "fa-solid fa-palette"},
    "ai": {"label": "AI / LLM", "icon": "fa-solid fa-brain"},
    "system": {"label": "System", "icon": "fa-solid fa-server"},
    "feature_flags": {"label": "Feature Flags", "icon": "fa-solid fa-flag"},
}
# Must include every category value used in the application_settings seed
# migration, plus "others" as a catch-all for uncategorized settings.
CATEGORY_ORDER = ["network", "graph", "connectors", "ui", "ai", "feature_flags", "system", "others"]


# ── Helpers ────────────────────────────────────────────────────────────


def _source_badge(source: str) -> Any:
    """Return a small coloured badge indicating the value source."""
    colors: dict[str, str] = {"db": "success", "env": "info", "default": "secondary"}
    return dbc.Badge(
        source,
        color=colors.get(source, "secondary"),
        className="ms-2",
        style={"fontSize": FONT_SIZE_XSMALL},
    )


def _build_setting_row(setting: dict[str, Any]) -> html.Div:
    """Build a single editable setting row."""
    key = setting["key"]
    value_type = setting["value_type"]
    effective = setting["effective_value"]
    source = setting["source"]
    description = setting.get("description", "")
    is_sensitive = setting.get("is_sensitive", False)
    apply_mode = setting.get("apply_mode", "dynamic")

    input_id = {"type": "settings-input", "key": key}

    if value_type == "boolean":
        input_component = dbc.Checklist(
            id=input_id,
            options=[{"label": "", "value": True}],
            value=[True] if effective else [],
            switch=True,
        )
    elif value_type == "integer":
        input_component = dbc.Input(
            id=input_id,
            type="number",
            value=effective,
            min=1,
            step=1,
            style={**INPUT_STYLE, "width": "140px"},
        )
    elif is_sensitive:
        input_component = dbc.Input(
            id=input_id,
            type="password",
            value=effective if effective else "",
            style={**INPUT_STYLE, "width": "260px"},
            placeholder="(sensitive — enter to change)",
        )
    else:
        input_component = dbc.Input(
            id=input_id,
            type="text",
            value=effective,
            style={**INPUT_STYLE, "width": "260px"},
        )

    reset_id = {"type": "settings-reset-btn", "key": key}

    # Apply-mode badge
    mode_badge = dbc.Badge(
        apply_mode,
        color="warning" if apply_mode == "restart" else "info",
        className="ms-1",
        style={"fontSize": FONT_SIZE_XTINY, "verticalAlign": "middle"},
    )

    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div(
                                [key, " ", mode_badge],
                                style={
                                    "fontFamily": FONT_SANS,
                                    "fontSize": FONT_SIZE_XSMALL,
                                    "fontWeight": FONT_WEIGHT_SEMIBOLD,
                                    "color": COLOR_CHARCOAL_MEDIUM,
                                    "textTransform": "uppercase",
                                    "letterSpacing": "0.5px",
                                    "marginBottom": "2px",
                                },
                            ),
                            html.Div(
                                description,
                                style={
                                    "fontFamily": FONT_SANS,
                                    "fontSize": FONT_SIZE_XSMALL,
                                    "color": COLOR_TEXT_MUTED,
                                    "lineHeight": "1.5",
                                },
                            ),
                        ],
                        width=5,
                    ),
                    dbc.Col(
                        html.Div(
                            input_component,
                            style={"display": "flex", "alignItems": "center"},
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        html.Div(
                            _source_badge(source),
                            style={"display": "flex", "alignItems": "center"},
                        ),
                        width=2,
                    ),
                    dbc.Col(
                        html.Div(
                            dbc.Button(
                                "Reset",
                                id=reset_id,
                                color="outline-secondary",
                                size="sm",
                                style={
                                    "fontFamily": FONT_SANS,
                                    "fontSize": FONT_SIZE_XSMALL,
                                },
                            ),
                            style={"display": "flex", "alignItems": "center"},
                        ),
                        width=2,
                    ),
                ],
                className="align-items-center",
                style={
                    "padding": f"{SPACING_XSMALL} 0",
                    "borderBottom": f"1px solid {COLOR_BORDER}",
                },
            ),
        ],
        id={"type": "settings-row", "key": key},
    )


def _build_category_section(category: str, settings: list[dict[str, Any]]) -> html.Div:
    """Build a collapsible section for a single category."""
    meta = CATEGORY_META.get(
        category, {"label": category, "icon": "fa-solid fa-gear"}
    )
    label = meta["label"]
    icon = meta["icon"]

    return html.Div(
        [
            html.Div(
                [
                    html.I(className=f"{icon} me-2", style={"color": COLOR_NAVY}),
                    html.Span(
                        label,
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_MEDIUM,
                            "fontWeight": FONT_WEIGHT_SEMIBOLD,
                            "color": COLOR_CHARCOAL_MEDIUM,
                            "textTransform": "uppercase",
                            "letterSpacing": "0.5px",
                        },
                    ),
                    html.Span(
                        f" ({len(settings)})",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_XSMALL,
                            "color": COLOR_GRAY_MEDIUM,
                            "marginLeft": SPACING_XXSMALL,
                        },
                    ),
                ],
                id={"type": "settings-category-toggle", "category": category},
                style={
                    "padding": f"{SPACING_XSMALL} {SPACING_SMALL}",
                    "cursor": "pointer",
                    "borderBottom": f"1px solid {COLOR_BORDER}",
                    "userSelect": "none",
                    "display": "flex",
                    "alignItems": "center",
                },
            ),
            dbc.Collapse(
                html.Div(
                    list(_build_setting_row(s) for s in settings),
                    style={
                        "padding": f"{SPACING_XSMALL} {SPACING_SMALL}",
                        "backgroundColor": COLOR_BACKGROUND_WHITE,
                    },
                ),
                id={"type": "settings-collapse", "category": category},
                is_open=True,
            ),
        ],
        style={
            "backgroundColor": COLOR_BACKGROUND_LIGHT,
            "border": f"1px solid {COLOR_BORDER}",
            "borderRadius": "2px",
            "marginBottom": SPACING_SMALL,
        },
    )


# ── Layout ─────────────────────────────────────────────────────────────


def get_layout() -> html.Div:
    """Return the settings page layout."""
    return html.Div(
        [
            dcc.Store(id="settings-store", data=None),
            dcc.Store(id="settings-initial-store", data=None),
            dcc.ConfirmDialog(
                id="settings-reset-all-confirm",
                message="Are you sure you want to reset ALL settings to their "
                        "default values? This cannot be undone.",
            ),
            html.Div(id="settings-feedback"),
            html.Div("Runtime Settings", style=PAGE_HEADER_STYLE),
            # Description + sticky action bar on the same row.
            html.Div(
                [
                    html.Div(
                        "Configure application behaviour without restarting "
                        "containers. Changes apply immediately.",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_GRAY_MEDIUM,
                            "lineHeight": "1.6",
                        },
                    ),
                    html.Div(
                        [
                            dbc.Button(
                                "Save All Changes",
                                id="settings-save-all",
                                color="primary",
                                style={
                                    **BUTTON_PRIMARY_STYLE,
                                    "marginRight": SPACING_XSMALL,
                                },
                            ),
                            dbc.Button(
                                "Reset All to Default",
                                id="settings-reset-all",
                                color="outline-danger",
                                size="sm",
                                style={
                                    "fontFamily": FONT_SANS,
                                    "fontSize": FONT_SIZE_XSMALL,
                                },
                            ),
                        ],
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "gap": SPACING_XSMALL,
                            "marginLeft": "auto",
                        },
                    ),
                ],
                style={
                    "position": "sticky",
                    "top": 0,
                    "zIndex": 10,
                    "backgroundColor": COLOR_BACKGROUND_WHITE,
                    "padding": f"{SPACING_XSMALL} 0",
                    "display": "flex",
                    "alignItems": "center",
                    "gap": SPACING_SMALL,
                    "borderBottom": f"1px solid {COLOR_BORDER}",
                    "marginBottom": SPACING_SMALL,
                },
            ),
            html.Div(id="settings-content"),
        ],
        style=CARD_CONTAINER_STYLE,
    )


# ── Callbacks ──────────────────────────────────────────────────────────


@callback(
    Output("settings-store", "data"),
    Input("url", "pathname"),
)
def load_settings(pathname: str) -> Any:
    """Fetch settings from the API when the settings page is visited."""
    if pathname not in ("/app/settings", "/app/settings/"):
        return no_update

    try:
        resp = requests.get(SETTINGS_API, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as exc:
        return {"status": "error", "message": str(exc)}


@callback(
    Output("settings-content", "children"),
    Output("settings-feedback", "children"),
    Output("settings-initial-store", "data"),
    Input("settings-store", "data"),
)
def render_settings(
    store: Any,
) -> tuple[list[Any], Any, dict[str, Any] | None]:
    """Render the settings grid grouped by category."""
    if store is None:
        return (
            [
                html.Div(
                    "Loading settings\u2026",
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": FONT_SIZE_SMALL,
                        "color": COLOR_GRAY_MEDIUM,
                    },
                )
            ],
            None,
            None,
        )

    if isinstance(store, dict) and store.get("status") == "error":
        return (
            [],
            create_alert(
                f"Failed to load settings: {store.get('message', 'Unknown error')}",
                color="danger",
                class_name="mb-3",
            ),
            None,
        )

    if not isinstance(store, list):
        return (
            [
                html.Div(
                    "Unexpected response format.",
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": FONT_SIZE_SMALL,
                        "color": COLOR_ERROR,
                    },
                )
            ],
            None,
            None,
        )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for setting in store:
        cat = setting.get("category") or "others"
        grouped.setdefault(cat, []).append(setting)

    sections = []
    for cat in CATEGORY_ORDER:
        cat_settings = grouped.get(cat, [])
        if not cat_settings:
            continue
        sections.append(
            dbc.Col(
                _build_category_section(cat, cat_settings),
                width=12,
                className="mb-3",
            )
        )

    initial = {
        s["key"]: {
            "value": s["effective_value"],
            "updated_at": s.get("updated_at"),
        }
        for s in store
    }
    return (sections, no_update, initial)


@callback(
    Output("settings-store", "data", allow_duplicate=True),
    Output("settings-feedback", "children", allow_duplicate=True),
    Input("settings-save-all", "n_clicks"),
    State("settings-initial-store", "data"),
    State({"type": "settings-input", "key": ALL}, "value"),
    State({"type": "settings-input", "key": ALL}, "id"),
    prevent_initial_call=True,
)
def save_all_settings(
    n_clicks: int | None,
    initial_data: dict[str, dict[str, Any]] | None,
    input_values: list[Any],
    input_ids: list[dict[str, str]],
) -> tuple[Any, Any]:
    """Save all changed settings via bulk PATCH."""
    if not n_clicks or not initial_data or not input_ids:
        raise PreventUpdate

    updates: dict[str, Any] = {}
    timestamps: list[str] = []
    for input_id, value in zip(input_ids, input_values):
        key = input_id["key"]
        # Normalise boolean checklist values: [True] → True, [] → False.
        if isinstance(value, list) and len(value) == 1 and value[0] is True:
            normalised = True
        elif isinstance(value, list) and len(value) == 0:
            normalised = False
        else:
            normalised = value

        entry = initial_data.get(key)
        if entry is None:
            continue
        if normalised != entry["value"]:
            updates[key] = normalised
            ts = entry.get("updated_at")
            if ts:
                timestamps.append(ts)

    if not updates:
        return no_update, create_alert(
            "No changes to save.",
            color="info",
            class_name="mb-3",
            duration=3000,
        )

    # Use the most recent loaded timestamp as the optimistic concurrency guard.
    # This ensures only changes made *after* the page was loaded trigger a conflict.
    expected_updated_at = max(timestamps) if timestamps else None

    try:
        resp = requests.patch(
            SETTINGS_API,
            json={
                "updates": updates,
                "expected_updated_at": expected_updated_at,
            },
            timeout=10,
        )
        if resp.status_code == 422:
            detail = resp.json()
            msg = detail.get("detail", str(detail))
            if isinstance(msg, list):
                msg = "; ".join(e.get("msg", str(e)) for e in msg)
            return no_update, create_alert(
                f"Validation error: {msg}", color="danger", class_name="mb-3"
            )
        if resp.status_code == 409:
            detail = resp.json().get("detail", {})
            msg = detail.get("detail", "Stale data \u2014 please reload and try again.")
            return no_update, create_alert(
                f"Conflict: {msg}", color="warning", class_name="mb-3"
            )
        resp.raise_for_status()
        result = resp.json()
        updated_count = len(result.get("updated", {}))
        warning = result.get("propagation_warning")

        # Reload to refresh the UI.
        reload_resp = requests.get(SETTINGS_API, timeout=10)
        reload_resp.raise_for_status()
        new_data = reload_resp.json()

        feedback = create_alert(
            f"Saved {updated_count} setting(s)." + (f" {warning}" if warning else ""),
            color="success",
            class_name="mb-3",
            duration=5000,
        )
        return new_data, feedback
    except requests.exceptions.RequestException as exc:
        return no_update, create_alert(
            f"Save failed: {exc}", color="danger", class_name="mb-3"
        )


@callback(
    Output("settings-store", "data", allow_duplicate=True),
    Output("settings-feedback", "children", allow_duplicate=True),
    Input({"type": "settings-reset-btn", "key": ALL}, "n_clicks"),
    State("settings-initial-store", "data"),
    prevent_initial_call=True,
)
def reset_single_setting(
    _n_clicks_list: list[int | None],
    initial_data: dict[str, dict[str, Any]] | None,
) -> tuple[Any, Any]:
    """Reset a single setting when its reset button is clicked."""
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate

    # Guard against spurious triggers when new buttons are rendered:
    # only proceed if at least one button was actually clicked.
    if not any(n is not None for n in _n_clicks_list):
        raise PreventUpdate

    trigger_id = ctx.triggered[0].get("prop_id", "")
    if not trigger_id:
        raise PreventUpdate

    try:
        prop_part = trigger_id.rsplit(".", 1)[0]
        parsed = json.loads(prop_part)
        key = parsed["key"]
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        raise PreventUpdate from exc

    # Get the timestamp loaded when the page was first rendered.
    entry = initial_data.get(key) if initial_data else None
    expected_updated_at = entry.get("updated_at") if entry else None

    try:
        resp = requests.post(
            f"{SETTINGS_API}{key}/reset",
            json={"expected_updated_at": expected_updated_at},
            timeout=10,
        )
        if resp.status_code == 422:
            detail = resp.json().get("detail", "Unknown error")
            return no_update, create_alert(
                f"Reset failed: {detail}", color="danger", class_name="mb-3"
            )
        if resp.status_code == 409:
            detail = resp.json().get("detail", {})
            msg = detail.get("detail", "Stale data \u2014 please reload and try again.")
            return no_update, create_alert(
                f"Conflict: {msg}", color="warning", class_name="mb-3"
            )
        resp.raise_for_status()

        reload_resp = requests.get(SETTINGS_API, timeout=10)
        reload_resp.raise_for_status()
        new_data = reload_resp.json()

        return new_data, create_alert(
            f"Reset {key} to default.",
            color="success",
            class_name="mb-3",
            duration=5000,
        )
    except requests.exceptions.RequestException as exc:
        return no_update, create_alert(
            f"Reset failed: {exc}", color="danger", class_name="mb-3"
        )


@callback(
    Output("settings-reset-all-confirm", "displayed"),
    Input("settings-reset-all", "n_clicks"),
    prevent_initial_call=True,
)
def confirm_reset_all(n_clicks: int | None) -> bool:
    """Show confirmation dialog before resetting all settings."""
    if not n_clicks:
        raise PreventUpdate
    return True


@callback(
    Output("settings-store", "data", allow_duplicate=True),
    Output("settings-feedback", "children", allow_duplicate=True),
    Input("settings-reset-all-confirm", "submit_n_clicks"),
    State("settings-initial-store", "data"),
    prevent_initial_call=True,
)
def reset_all_settings(
    n_clicks: int | None,
    initial_data: dict[str, dict[str, Any]] | None,
) -> tuple[Any, Any]:
    """Reset all settings to their env/default values."""
    if not n_clicks:
        raise PreventUpdate

    # Use the most recent loaded timestamp as the optimistic concurrency guard.
    # This ensures only changes made *after* the page was loaded trigger a conflict.
    timestamps = [
        entry["updated_at"]
        for entry in (initial_data or {}).values()
        if entry.get("updated_at")
    ]
    expected_updated_at = max(timestamps) if timestamps else None

    try:
        resp = requests.post(
            f"{SETTINGS_API}reset",
            json={"expected_updated_at": expected_updated_at},
            timeout=10,
        )
        if resp.status_code == 409:
            detail = resp.json().get("detail", {})
            msg = detail.get("detail", "Stale data \u2014 please reload and try again.")
            return no_update, create_alert(
                f"Conflict: {msg}", color="warning", class_name="mb-3"
            )
        resp.raise_for_status()

        reload_resp = requests.get(SETTINGS_API, timeout=10)
        reload_resp.raise_for_status()
        new_data = reload_resp.json()

        return new_data, create_alert(
            "All settings reset to defaults.",
            color="success",
            class_name="mb-3",
            duration=5000,
        )
    except requests.exceptions.RequestException as exc:
        return no_update, create_alert(
            f"Reset all failed: {exc}", color="danger", class_name="mb-3"
        )


# Toggle category collapse sections via a clientside callback for responsiveness.
clientside_callback(
    """
    function(n_clicks, is_open) {
        return !is_open;
    }
    """,
    Output({"type": "settings-collapse", "category": MATCH}, "is_open"),
    Input({"type": "settings-category-toggle", "category": MATCH}, "n_clicks"),
    State({"type": "settings-collapse", "category": MATCH}, "is_open"),
    prevent_initial_call=True,
)
