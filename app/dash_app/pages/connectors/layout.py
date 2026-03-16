"""Dash layouts for the Connectors pages."""

from dash import dcc, html
import dash_bootstrap_components as dbc

from app.dash_app.components.common import create_page_header
from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.dash_app.styles import (
    CARD_CONTAINER_STYLE,
    COLOR_GRAY_MEDIUM,
    COLOR_CHARCOAL_MEDIUM,
    FONT_SANS,
    FONT_SIZE_SMALL,
    FONT_SIZE_MEDIUM,
    FONT_WEIGHT_MEDIUM,
    COLOR_BORDER,
    SPACING_XSMALL,
    SPACING_SMALL,
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
                    dcc.Interval(
                        id="connectors-load",
                        interval=500,
                        n_intervals=0,
                        max_intervals=1,
                    ),
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

    return html.Div(
        [
            create_page_header("Connectors"),
            html.Div(
                [
                    html.Div(
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
                    ),
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
                        "Connector detail scaffold - coming soon.",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_GRAY_MEDIUM,
                        },
                    ),
                    html.Div(
                        id="connector-detail-root",
                        children=[],
                        style={
                            "marginTop": SPACING_SMALL,
                            "borderTop": f"1px solid {COLOR_BORDER}",
                            "paddingTop": SPACING_SMALL,
                        },
                    ),
                ],
                style=CARD_CONTAINER_STYLE,
            ),
        ]
    )
