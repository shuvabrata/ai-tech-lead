"""Analytics gallery page for pre-built graph visualizations."""

from dash import html
import dash_bootstrap_components as dbc

from app.analytics.registry import GRAPH_ANALYTICS
from app.dash_app.components.common import create_page_header
from app.dash_app.styles import (
    CARD_CONTAINER_STYLE,
    COLOR_BACKGROUND_WHITE,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_DARK,
    COLOR_GRAY_MEDIUM,
    FONT_SANS,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_WEIGHT_MEDIUM,
    SPACING_MEDIUM,
    SPACING_SMALL,
    SPACING_XSMALL,
)


def get_layout():
    """Return the analytics gallery page."""
    return html.Div(
        [
            create_page_header("Analytics"),
            html.Div(
                [
                    html.Div(
                        "Launch pre-built graph visualizations for common leadership and delivery questions.",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_GRAY_MEDIUM,
                            "marginBottom": SPACING_MEDIUM,
                        },
                    ),
                    dbc.Row(
                        [
                            dbc.Col(_create_analytic_card(analytic), md=6, className="mb-3")
                            for analytic in GRAPH_ANALYTICS
                        ],
                        className="g-3",
                    ),
                ],
                style=CARD_CONTAINER_STYLE,
            ),
        ],
        className="mt-3",
    )


def _create_analytic_card(analytic) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.I(className=analytic.icon, style={"fontSize": "20px", "color": COLOR_CHARCOAL_MEDIUM}),
                        html.Span(
                            analytic.title,
                            style={
                                "fontFamily": FONT_SANS,
                                "fontSize": FONT_SIZE_LARGE,
                                "fontWeight": FONT_WEIGHT_MEDIUM,
                                "color": COLOR_GRAY_DARK,
                                "marginLeft": SPACING_XSMALL,
                            },
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center", "marginBottom": SPACING_SMALL},
                ),
                html.Div(
                    analytic.description,
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": FONT_SIZE_MEDIUM,
                        "color": COLOR_GRAY_MEDIUM,
                        "lineHeight": "1.6",
                        "marginBottom": SPACING_MEDIUM,
                    },
                ),
                dbc.Button("Open Visualization", href=analytic.href, color="primary", size="sm"),
            ]
        ),
        style={
            "backgroundColor": COLOR_BACKGROUND_WHITE,
            "border": f"1px solid {COLOR_BORDER}",
            "borderRadius": "2px",
            "padding": SPACING_SMALL,
            "minHeight": "220px",
            "boxShadow": "none",
        },
    )
