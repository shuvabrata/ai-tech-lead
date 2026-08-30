"""Graph Styling settings page layout.

Provides a user-configurable editor for graph themes (colors, shapes, sizes,
and edge/global styling). The layout renders two base-mode sections
(executive-light / executive-dark), each containing a grid of node-type cards
plus an Edges card and a Global card.

The live preview and actions (save/clone/set-default/delete) are implemented
in later phases of Plan 017; this module currently builds the static editor
layout only.
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

from .components import build_base_mode_tabs


def _breadcrumb() -> html.Div:
    """Breadcrumb trail (Settings / Graph Styling)."""
    return html.Div(
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
    )


def get_layout() -> html.Div:
    """Return the Graph Styling settings page layout."""
    return html.Div(
        [
            _breadcrumb(),
            create_page_header("Graph Styling"),
            html.Div(
                "Customize graph colors, shapes, sizes, and node appearance.",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_SMALL,
                    "color": COLOR_GRAY_MEDIUM,
                    "lineHeight": "1.6",
                    "marginBottom": SPACING_SMALL,
                },
            ),
            html.Div(id="gs-page-feedback"),
            dcc.Store(id="gs-set-default-pending", data=None),
            dcc.Store(id="gs-delete-pending", data=None),
            dcc.ConfirmDialog(
                id="gs-set-default-confirm",
                message="Set this theme as the default for its base mode? "
                        "The previous default will be replaced.",
            ),
            dcc.ConfirmDialog(
                id="gs-delete-confirm",
                message="Delete this theme? This cannot be undone.",
            ),
            build_base_mode_tabs(),
        ],
        style=CARD_CONTAINER_STYLE,
    )
