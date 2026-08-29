"""Graph Styling settings page layout.

Provides a user-configurable editor for graph themes (colors, shapes, sizes,
and edge/global styling). This module currently renders a placeholder shell;
the full editor (base-mode sections, node-type cards, live preview, and
actions) is implemented in later phases of Plan 017.
"""

from __future__ import annotations

from dash import dcc, html

from app.dash_app.components.common import create_page_header
from app.dash_app.styles import (
    CARD_CONTAINER_STYLE,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_MEDIUM,
    FONT_SANS,
    FONT_SIZE_SMALL,
    SPACING_SMALL,
    SPACING_XSMALL,
)


def get_layout() -> html.Div:
    """Return the Graph Styling settings page layout (placeholder shell)."""
    return html.Div(
        [
            html.Div(
                [
                    dcc.Link(
                        "Settings",
                        href="/app/settings",
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
                        "Graph Styling",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": FONT_SIZE_SMALL,
                            "color": COLOR_CHARCOAL_MEDIUM,
                        },
                    ),
                ],
                style={"marginBottom": SPACING_SMALL},
            ),
            create_page_header("Graph Styling"),
            html.Div(
                "Customize graph colors, shapes, sizes, and node appearance. "
                "The editor will appear here in a future update.",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_SMALL,
                    "color": COLOR_GRAY_MEDIUM,
                    "lineHeight": "1.6",
                },
            ),
        ],
        style=CARD_CONTAINER_STYLE,
    )
