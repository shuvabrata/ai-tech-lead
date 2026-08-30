"""Settings hub page layout.

Displays a grid of cards linking to settings sub-pages (Runtime Settings,
AI Prompt Control, Graph Styling).
"""

from dash import html
import dash_bootstrap_components as dbc

from app.dash_app.components.common import create_page_header
from app.dash_app.styles import CARD_CONTAINER_STYLE
from .components.settings_card import settings_card


def get_layout() -> html.Div:
    """Return the settings hub page layout."""
    cards = [
        settings_card(
            card_id="runtime",
            title="Runtime Settings",
            icon="fa-solid fa-sliders",
            description="Configure application behaviour.",
            href="/app/settings/runtime",
        ),
        settings_card(
            card_id="ai-prompt-control",
            title="AI Prompt Control",
            icon="fa-solid fa-brain",
            description="Manage system prompts and AI response controls.",
            coming_soon=True,
        ),
        settings_card(
            card_id="graph-styling",
            title="Graph Styling",
            icon="fa-solid fa-palette",
            description="Customize graph colors, labels, and node appearance.",
            href="/app/settings/graph-styling",
        ),
    ]

    return html.Div(
        [
            create_page_header(
                [("Settings", None)],
                "Manage runtime configuration, AI behaviour, and graph appearance.",
            ),
            html.Div(
                dbc.Row(
                    [
                        dbc.Col(card, md=3, sm=6, xs=12)
                        for card in cards
                    ],
                    className="g-3",
                ),
                style=CARD_CONTAINER_STYLE,
            ),
        ],
    )