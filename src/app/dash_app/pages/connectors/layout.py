"""Dash layouts for the Connectors pages."""

import uuid

from dash import dcc, html
import dash_bootstrap_components as dbc

from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.dash_app.components.common import create_alert, create_page_header
from app.dash_app.styles import (
    CARD_CONTAINER_STYLE,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_CODE_BACKGROUND,
    COLOR_GRAY_MEDIUM,
    FONT_SANS,
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
from .components.tooltips import FIELD_TOOLTIPS


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
    setup_type = connector_meta.get("setup_type", "db_backed")
    supports_items = connector_meta.get("supports_items", True)
    form_spec = CONFIG_FORM_SPECS.get(connector_type, {})

    if setup_type == "manual":
        return _get_manual_setup_layout(connector_type, connector_meta)

    if not form_spec:
        return html.Div(
            [
                create_page_header("Connectors"),
                create_alert(
                    f"Unknown connector type: {connector_type}",
                    color="warning",
                    class_name="mt-3",
                ),
            ]
        )

    return html.Div(
        [
            create_page_header("Connectors"),
            html.Div(
                [
                    _breadcrumb(display_name),
                    dcc.Store(id="connector-detail-store", storage_type="memory"),
                    dcc.Store(id="connector-items-store", storage_type="memory"),
                    dcc.Store(id="connector-edit-item", storage_type="memory"),
                    dcc.Store(
                        id={"type": "connector-search-filters-store", "connector_type": connector_type},
                        storage_type="memory",
                    ),
                    html.Div(
                        id="connector-action-feedback",
                        key=f"connector-feedback-{connector_type}-{uuid.uuid4()}",
                        style={
                            "position": "sticky",
                            "top": SPACING_SMALL,
                            "zIndex": 1000,
                            "marginBottom": SPACING_SMALL,
                        },
                    ),
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
                        style={"marginBottom": SPACING_SMALL, "display": "none" if not supports_items else "block"},
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
            _render_search_filters_editor(connector_type),
            html.Div(
                [
                    dbc.Button(
                        "Add Item",
                        id={"type": "connector-item-add", "connector_type": connector_type},
                        color="primary",
                        size="sm",
                        className="me-2",
                    ),
                    dbc.Button(
                        "Clear Form",
                        id={"type": "connector-item-cancel", "connector_type": connector_type},
                        color="outline-secondary",
                        size="sm",
                    ),
                ],
                className="mt-2"
            )
        ]
    )


def _render_search_filters_editor(connector_type: str) -> html.Div:
    if connector_type != "github":
        return html.Div()

    tooltip_id = f"tooltip-target-{connector_type}-search-filters"

    return html.Div(
        [
            html.Div(
                [
                    html.Span("SEARCH FILTERS"),
                    html.I(
                        className="fas fa-info-circle",
                        id=tooltip_id,
                        style={"cursor": "help", "marginLeft": "6px", "color": COLOR_GRAY_MEDIUM},
                    ),
                    dbc.Tooltip(
                        (
                            "Search filters let you tag a repository with custom key/value metadata "
                            "for downstream filtering and analysis. Add any string key (for example, "
                            "props.division) and value (for example, platform). These filters do not "
                            "change GitHub data collection; they help scope and segment results in "
                            "analytics and queries."
                        ),
                        target=tooltip_id,
                        placement="top",
                    ),
                ],
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_SMALL,
                    "color": COLOR_GRAY_MEDIUM,
                    "marginTop": SPACING_SMALL,
                    "marginBottom": SPACING_XSMALL,
                    "letterSpacing": "0.5px",
                    "display": "flex",
                    "alignItems": "center",
                },
            ),
            html.Div(
                "Add one or more key/value filters. Values are stored as strings.",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_SMALL,
                    "color": COLOR_GRAY_MEDIUM,
                    "marginBottom": SPACING_XSMALL,
                },
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Input(
                            id={
                                "type": "connector-search-filter-key",
                                "connector_type": connector_type,
                            },
                            type="text",
                            placeholder="props.application-context",
                        ),
                        md=5,
                        xs=12,
                    ),
                    dbc.Col(
                        dbc.Input(
                            id={
                                "type": "connector-search-filter-value",
                                "connector_type": connector_type,
                            },
                            type="text",
                            placeholder="production",
                        ),
                        md=5,
                        xs=12,
                    ),
                    dbc.Col(
                        dbc.Button(
                            "Add Filter",
                            id={
                                "type": "connector-search-filter-add",
                                "connector_type": connector_type,
                            },
                            color="outline-secondary",
                            size="sm",
                            className="w-100",
                        ),
                        md=2,
                        xs=12,
                    ),
                ],
                className="g-2",
            ),
            html.Div(
                id={"type": "connector-search-filter-list", "connector_type": connector_type},
                style={"marginTop": SPACING_XSMALL},
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

    icon_id = f"tooltip-target-{connector_type}-{section}-{field['key']}"
    tooltip_text = FIELD_TOOLTIPS.get(connector_type, {}).get(field["key"])

    label_children = [html.Span(field.get("label", field["key"]).upper())]

    if field.get("required"):
        label_children.append(
            html.Span(
                " *",
                style={
                    "color": "#b42318",
                    "fontWeight": FONT_WEIGHT_MEDIUM,
                    "marginLeft": "2px",
                },
            )
        )
    
    if tooltip_text:
        label_children.append(
            html.I(
                className="fas fa-info-circle",
                id=icon_id,
                style={"cursor": "help", "marginLeft": "6px", "color": COLOR_GRAY_MEDIUM}
            )
        )
        label_children.append(
            dbc.Tooltip(
                tooltip_text,
                target=icon_id,
                placement="top",
            )
        )

    label = html.Div(
        label_children,
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_SMALL,
            "color": COLOR_GRAY_MEDIUM,
            "marginBottom": SPACING_XSMALL,
            "letterSpacing": "0.5px",
            "display": "flex",
            "alignItems": "center",
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
        control = dcc.Dropdown(id=field_id, options=options, value=field.get("default", []), multi=True)
    else:
        control = dbc.Input(id=field_id, type="text", placeholder=placeholder)

    return html.Div([label, control])


def _get_manual_setup_layout(connector_type: str, connector_meta: dict) -> html.Div:
    """Render a manual setup guidance page for connectors that are env/Docker-managed."""
    display_name = connector_meta.get("display_name", connector_type)

    def _env_row(var: str, description: str) -> html.Tr:
        return html.Tr(
            [
                html.Td(
                    html.Code(
                        var,
                        style={
                            "fontFamily": "monospace",
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_CHARCOAL_MEDIUM,
                            "backgroundColor": COLOR_CODE_BACKGROUND,
                            "padding": "2px 6px",
                            "borderRadius": "2px",
                        },
                    ),
                    style={"padding": f"{SPACING_XSMALL} {SPACING_SMALL} {SPACING_XSMALL} 0", "whiteSpace": "nowrap"},
                ),
                html.Td(
                    description,
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": FONT_SIZE_SMALL,
                        "color": COLOR_GRAY_MEDIUM,
                        "padding": SPACING_XSMALL,
                    },
                ),
            ]
        )

    return html.Div(
        [
            create_page_header("Connectors"),
            html.Div(
                [
                    _breadcrumb(display_name),
                    # Required stores — callbacks still fire on all detail pages
                    dcc.Store(id="connector-detail-store", storage_type="memory"),
                    dcc.Store(id="connector-items-store", storage_type="memory"),
                    dcc.Store(id="connector-edit-item", storage_type="memory"),
                    dcc.Store(
                        id={"type": "connector-search-filters-store", "connector_type": connector_type},
                        storage_type="memory",
                    ),
                    html.Div(
                        id="connector-action-feedback",
                        key=f"connector-feedback-{connector_type}",
                        style={
                            "position": "sticky",
                            "top": SPACING_SMALL,
                            "zIndex": 1000,
                            "marginBottom": SPACING_SMALL,
                        },
                    ),
                    # Hidden items list element — required for shared render_items_list callback
                    html.Div(id="connector-items-list", style={"display": "none"}),
                    # Setup method notice
                    html.Div(
                        [
                            _section_title("Setup Method"),
                            html.Div(
                                [
                                    html.I(className="fa-solid fa-circle-info me-2", style={"color": "#4299e1"}),
                                    html.Span(
                                        "GitHub MCP Server is configured through Docker Compose environment "
                                        "variables. Credentials are not stored in the database for this connector.",
                                        style={
                                            "fontFamily": FONT_SANS,
                                            "fontSize": FONT_SIZE_SMALL,
                                            "color": COLOR_CHARCOAL_MEDIUM,
                                        },
                                    ),
                                ],
                                style={
                                    "display": "flex",
                                    "alignItems": "flex-start",
                                    "padding": SPACING_SMALL,
                                    "backgroundColor": COLOR_CODE_BACKGROUND,
                                    "border": f"1px solid {COLOR_BORDER}",
                                    "borderRadius": "2px",
                                    "marginBottom": SPACING_SMALL,
                                },
                            ),
                        ],
                        style={"marginBottom": SPACING_SMALL},
                    ),
                    # App service env vars
                    html.Div(
                        [
                            _section_title("App Service — Required Variables"),
                            html.Div(
                                "Set these in the",
                                style={"fontFamily": FONT_SANS, "fontSize": FONT_SIZE_SMALL, "color": COLOR_GRAY_MEDIUM, "marginBottom": SPACING_XSMALL, "display": "inline"},
                            ),
                            html.Code(
                                " app ",
                                style={"fontFamily": "monospace", "fontSize": FONT_SIZE_SMALL, "color": COLOR_CHARCOAL_MEDIUM, "backgroundColor": COLOR_CODE_BACKGROUND, "padding": "2px 6px", "borderRadius": "2px"},
                            ),
                            html.Div(
                                "service environment in docker-compose.yml:",
                                style={"fontFamily": FONT_SANS, "fontSize": FONT_SIZE_SMALL, "color": COLOR_GRAY_MEDIUM, "marginBottom": SPACING_SMALL, "display": "inline"},
                            ),
                            html.Table(
                                [
                                    html.Tbody(
                                        [
                                            _env_row("GITHUB_MCP_ENABLED", "Set to true to enable the GitHub MCP integration in the AI agent."),
                                            _env_row("GITHUB_MCP_SERVER_URL", "The URL of the running GitHub MCP sidecar service (e.g., http://github-mcp:8080)."),
                                            _env_row("GITHUB_MCP_TOKEN", "A GitHub personal access token passed to the MCP client manager."),
                                        ]
                                    )
                                ],
                                style={"width": "100%", "borderCollapse": "collapse"},
                            ),
                        ],
                        style={
                            "marginBottom": SPACING_SMALL,
                            "padding": SPACING_SMALL,
                            "border": f"1px solid {COLOR_BORDER}",
                            "borderRadius": "2px",
                        },
                    ),
                    # github-mcp sidecar env vars
                    html.Div(
                        [
                            _section_title("GitHub MCP Sidecar — Required Variables"),
                            html.Div(
                                "Set this in the",
                                style={"fontFamily": FONT_SANS, "fontSize": FONT_SIZE_SMALL, "color": COLOR_GRAY_MEDIUM, "marginBottom": SPACING_XSMALL, "display": "inline"},
                            ),
                            html.Code(
                                " github-mcp ",
                                style={"fontFamily": "monospace", "fontSize": FONT_SIZE_SMALL, "color": COLOR_CHARCOAL_MEDIUM, "backgroundColor": COLOR_CODE_BACKGROUND, "padding": "2px 6px", "borderRadius": "2px"},
                            ),
                            html.Div(
                                "service environment in docker-compose.yml:",
                                style={"fontFamily": FONT_SANS, "fontSize": FONT_SIZE_SMALL, "color": COLOR_GRAY_MEDIUM, "marginBottom": SPACING_SMALL, "display": "inline"},
                            ),
                            html.Table(
                                [
                                    html.Tbody(
                                        [
                                            _env_row("GITHUB_PERSONAL_ACCESS_TOKEN", "A GitHub personal access token with repository read permissions for the MCP sidecar process."),
                                        ]
                                    )
                                ],
                                style={"width": "100%", "borderCollapse": "collapse"},
                            ),
                        ],
                        style={
                            "marginBottom": SPACING_SMALL,
                            "padding": SPACING_SMALL,
                            "border": f"1px solid {COLOR_BORDER}",
                            "borderRadius": "2px",
                        },
                    ),
                    # Restart guidance
                    html.Div(
                        [
                            _section_title("Applying Changes"),
                            html.Div(
                                "After editing environment variables in docker-compose.yml, restart the affected services:",
                                style={"fontFamily": FONT_SANS, "fontSize": FONT_SIZE_SMALL, "color": COLOR_GRAY_MEDIUM, "marginBottom": SPACING_XSMALL},
                            ),
                            html.Pre(
                                "docker compose stop app github-mcp\ndocker compose up -d app github-mcp",
                                style={
                                    "fontFamily": "monospace",
                                    "fontSize": FONT_SIZE_SMALL,
                                    "color": COLOR_CHARCOAL_MEDIUM,
                                    "backgroundColor": COLOR_CODE_BACKGROUND,
                                    "border": f"1px solid {COLOR_BORDER}",
                                    "borderRadius": "2px",
                                    "padding": SPACING_SMALL,
                                    "margin": 0,
                                    "overflowX": "auto",
                                },
                            ),
                        ],
                        style={
                            "marginBottom": SPACING_SMALL,
                            "padding": SPACING_SMALL,
                            "border": f"1px solid {COLOR_BORDER}",
                            "borderRadius": "2px",
                        },
                    ),
                ],
                style=CARD_CONTAINER_STYLE,
            ),
        ],
        className="mt-3",
    )
