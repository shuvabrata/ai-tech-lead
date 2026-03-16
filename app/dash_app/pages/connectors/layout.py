"""Dash layouts for the Connectors pages."""

import uuid

from dash import dcc, html
import dash_bootstrap_components as dbc

from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.dash_app.components.common import create_page_header
from app.dash_app.styles import (
    CARD_CONTAINER_STYLE,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_MEDIUM,
    FONT_SANS,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_WEIGHT_MEDIUM,
    SPACING_XSMALL,
    SPACING_SMALL,
)
from .components.config_forms import (
    CONFIG_FORM_SPECS,
    FIELD_CHECKBOX,
    FIELD_MULTISELECT,
    FIELD_NUMBER,
    FIELD_PASSWORD,
    FIELD_TEXT,
    FIELD_TEXTAREA,
)


def get_layout():
    return html.Div(
        [
            create_page_header("Connectors"),
            html.Div(
                [
                    html.Div(
                        "Manage external integrations and verify connectivity.",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_GRAY_MEDIUM,
                            "marginBottom": SPACING_SMALL,
                        },
                    ),
                    dcc.Store(id="connectors-store", storage_type="memory"),
                    dcc.Loading(
                        id="connectors-loading",
                        type="circle",
                        children=html.Div(
                            dbc.Row(
                                id="connectors-grid",
                                className="g-3",
                                children=[
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
                                ],
                            )
                        ),
                    ),
                ],
                style=CARD_CONTAINER_STYLE,
            ),
        ],
        className="mt-3",
    )


def get_detail_layout(connector_type: str):
    connector_meta = CONNECTOR_REGISTRY.get(connector_type, {})
    display_name = connector_meta.get("display_name", connector_type)
    form_spec = CONFIG_FORM_SPECS.get(connector_type, {})

    if not form_spec:
        return html.Div(
            [
                create_page_header("Connectors"),
                dbc.Alert(
                    f"Unknown connector type: {connector_type}",
                    color="warning",
                    className="mt-3",
                ),
            ]
        )

    return html.Div(
        [
            create_page_header("Connectors"),
            html.Div(
                [
                    _breadcrumb(display_name),
                    html.Div(
                        display_name,
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_MEDIUM,
                            "fontWeight": FONT_WEIGHT_MEDIUM,
                            "color": COLOR_CHARCOAL_MEDIUM,
                            "marginBottom": SPACING_XSMALL,
                        },
                    ),
                    html.Div(
                        "Configure connector settings and managed items below.",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_GRAY_MEDIUM,
                            "marginBottom": SPACING_SMALL,
                        },
                    ),
                    dcc.Store(id="connector-detail-store", storage_type="memory"),
                    dcc.Store(id="connector-items-store", storage_type="memory"),
                    dcc.Store(id="connector-edit-item", storage_type="memory"),
                    html.Div(
                        [
                            _section_title("Connector Settings"),
                            _render_connector_config(form_spec, connector_type),
                            dbc.Button(
                                "Save Configuration",
                                id={"type": "connector-save", "connector_type": connector_type},
                                color="primary",
                                size="sm",
                                className="mt-2",
                            ),
                        ],
                        style={"marginBottom": SPACING_SMALL},
                    ),
                    html.Div(
                        [
                            _section_title("Configured Items"),
                            _render_item_form(form_spec, connector_type),
                            html.Div(
                                id="connector-items-list",
                                children=[
                                    html.Div(
                                        "No items configured yet.",
                                        style={
                                            "fontFamily": FONT_SANS,
                                            "fontSize": FONT_SIZE_SMALL,
                                            "color": COLOR_GRAY_MEDIUM,
                                            "paddingTop": SPACING_XSMALL,
                                        },
                                    )
                                ],
                                style={
                                    "marginTop": SPACING_SMALL,
                                    "borderTop": f"1px solid {COLOR_BORDER}",
                                    "paddingTop": SPACING_SMALL,
                                },
                            ),
                        ],
                        style={"marginBottom": SPACING_SMALL},
                    ),
                    html.Div(
                        [
                            dbc.Button(
                                "Test Connection",
                                id={"type": "connector-test", "connector_type": connector_type},
                                color="secondary",
                                size="sm",
                                className="me-2",
                            ),
                            dbc.Button(
                                "Delete Configuration",
                                id={"type": "connector-delete", "connector_type": connector_type},
                                color="danger",
                                size="sm",
                            ),
                        ]
                    ),
                    html.Div(
                        id="connector-action-feedback",
                        className="mt-2",
                        key=f"connector-feedback-{connector_type}-{uuid.uuid4()}",
                    ),
                ],
                style=CARD_CONTAINER_STYLE,
            ),
        ],
        className="mt-3",
    )


def _breadcrumb(display_name: str) -> html.Div:
    return html.Div(
        [
            dcc.Link(
                "Connectors",
                href="/app/connectors",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_SMALL,
                    "color": COLOR_GRAY_MEDIUM,
                    "textDecoration": "none",
                },
            ),
            html.Span(
                " / ",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_SMALL,
                    "color": COLOR_GRAY_MEDIUM,
                    "margin": f"0 {SPACING_XSMALL}",
                },
            ),
            html.Span(
                display_name,
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_SMALL,
                    "color": COLOR_CHARCOAL_MEDIUM,
                },
            ),
        ],
        style={"marginBottom": SPACING_SMALL},
    )


def _section_title(text: str) -> html.Div:
    return html.Div(
        text,
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_SMALL,
            "color": COLOR_CHARCOAL_MEDIUM,
            "fontWeight": FONT_WEIGHT_MEDIUM,
            "marginBottom": SPACING_XSMALL,
            "textTransform": "uppercase",
            "letterSpacing": "0.5px",
        },
    )


def _render_connector_config(form_spec: dict, connector_type: str) -> html.Div:
    fields = form_spec.get("connector_config", [])
    if not fields:
        return html.Div(
            "No connector-level settings required.",
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_SMALL,
                "color": COLOR_GRAY_MEDIUM,
            },
        )

    field_components = [
        dbc.Col(_render_field(field, connector_type, section="connector"), md=6, xs=12)
        for field in fields
    ]
    return dbc.Row(field_components, className="g-3")


def _render_item_form(form_spec: dict, connector_type: str) -> html.Div:
    item_spec = form_spec.get("item", {})
    fields = item_spec.get("fields", [])
    if not fields:
        return html.Div(
            "No item configuration available.",
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_SMALL,
                "color": COLOR_GRAY_MEDIUM,
            },
        )

    field_components = [
        dbc.Col(_render_field(field, connector_type, section="item"), md=6, xs=12)
        for field in fields
    ]
    return html.Div(
        [
            html.Div(
                item_spec.get("label", "Item"),
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_SMALL,
                    "color": COLOR_CHARCOAL_MEDIUM,
                    "fontWeight": FONT_WEIGHT_MEDIUM,
                    "marginBottom": SPACING_XSMALL,
                },
            ),
            dbc.Row(field_components, className="g-3"),
            dbc.Button(
                "Add Item",
                id={"type": "connector-item-add", "connector_type": connector_type},
                color="primary",
                size="sm",
                className="mt-2",
            ),
        ]
    )


def _render_field(field: dict, connector_type: str, section: str) -> html.Div:
    field_id = {
        "type": "connector-field",
        "connector_type": connector_type,
        "section": section,
        "field": field["key"],
    }

    label = html.Div(
        field.get("label", field["key"]).upper(),
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_SMALL,
            "color": COLOR_GRAY_MEDIUM,
            "marginBottom": SPACING_XSMALL,
            "letterSpacing": "0.5px",
        },
    )

    input_type = field.get("input_type", FIELD_TEXT)
    placeholder = field.get("placeholder")

    if input_type == FIELD_TEXTAREA:
        control = dbc.Textarea(id=field_id, placeholder=placeholder, rows=3)
    elif input_type == FIELD_PASSWORD:
        control = dbc.Input(id=field_id, type="password", placeholder=placeholder)
    elif input_type == FIELD_NUMBER:
        control = dbc.Input(id=field_id, type="number", placeholder=placeholder)
    elif input_type == FIELD_CHECKBOX:
        control = dbc.Switch(id=field_id, label="", value=False)
    elif input_type == FIELD_MULTISELECT:
        options = field.get("options", [])
        control = dcc.Dropdown(id=field_id, options=options, value=[], multi=True)
    else:
        control = dbc.Input(id=field_id, type="text", placeholder=placeholder)

    return html.Div([label, control])
