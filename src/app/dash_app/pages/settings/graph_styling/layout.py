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
from app.dash_app.styles import CARD_CONTAINER_STYLE

from .components import build_base_mode_tabs


def get_layout() -> html.Div:
    """Return the Graph Styling settings page layout."""
    return html.Div(
        [
            create_page_header(
                [("Settings", "/app/settings"), ("Graph Styling", None)],
                "Customize graph colors, shapes, sizes, and node appearance.",
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
