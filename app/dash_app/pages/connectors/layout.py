"""Dash layouts for the Connectors pages."""

from dash import dcc, html
import dash_bootstrap_components as dbc

from app.dash_app.components.common import create_page_header
from app.dash_app.styles import (
    CARD_CONTAINER_STYLE,
    COLOR_GRAY_MEDIUM,
    FONT_SANS,
    FONT_SIZE_SMALL,
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
    return html.Div(
        [
            html.H2(f"Connector: {connector_type}"),
            html.P("Connector detail scaffold - coming soon."),
        ]
    )
