"""Connector card component."""

from dash import html

from app.dash_app.styles import (
    COLOR_BACKGROUND_LIGHT,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_ERROR,
    COLOR_GRAY_LIGHT,
    COLOR_GRAY_MEDIUM,
    COLOR_SUCCESS,
    FONT_SANS,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_WEIGHT_MEDIUM,
    SPACING_XXSMALL,
    SPACING_XSMALL,
    SPACING_SMALL,
)


STATUS_COLORS = {
    "connected": COLOR_SUCCESS,
    "error": COLOR_ERROR,
    "not_configured": COLOR_GRAY_LIGHT,
}


def _format_status(status: str) -> str:
    return status.replace("_", " ").title()


def connector_card(
    connector_type: str,
    display_name: str,
    icon: str,
    status: str,
):
    status_color = STATUS_COLORS.get(status, COLOR_GRAY_LIGHT)

    return html.Div(
        [
            html.Div(
                [
                    html.I(
                        className=icon,
                        style={
                            "fontSize": "20px",
                            "color": COLOR_CHARCOAL_MEDIUM,
                            "marginRight": SPACING_XSMALL,
                        },
                    ),
                    html.Div(
                        display_name,
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_MEDIUM,
                            "fontWeight": FONT_WEIGHT_MEDIUM,
                            "color": COLOR_CHARCOAL_MEDIUM,
                        },
                    ),
                ],
                style={"display": "flex", "alignItems": "center"},
            ),
            html.Div(
                [
                    html.Span(
                        "",
                        style={
                            "display": "inline-block",
                            "width": "8px",
                            "height": "8px",
                            "borderRadius": "50%",
                            "backgroundColor": status_color,
                            "marginRight": SPACING_XXSMALL,
                        },
                    ),
                    html.Span(
                        _format_status(status),
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_GRAY_MEDIUM,
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "marginTop": SPACING_XSMALL,
                },
            ),
        ],
        id={"type": "connector-card", "connector_type": connector_type},
        n_clicks=0,
        className="connector-card",
        style={
            "padding": SPACING_SMALL,
            "backgroundColor": COLOR_BACKGROUND_LIGHT,
            "border": f"1px solid {COLOR_BORDER}",
            "borderRadius": "2px",
            "cursor": "pointer",
            "userSelect": "none",
        },
    )
