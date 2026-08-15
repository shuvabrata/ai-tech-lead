"""Settings hub card component.

A card used on the Settings hub page to navigate to sub-pages or show
placeholder cards for upcoming features.
"""

from dash import html
import dash_bootstrap_components as dbc

from app.dash_app.styles import (
    COLOR_BACKGROUND_LIGHT,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_MEDIUM,
    COLOR_NAVY,
    FONT_SANS,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    FONT_SIZE_XTINY,
    FONT_WEIGHT_MEDIUM,
    SPACING_XSMALL,
    SPACING_SMALL,
)


def settings_card(
    card_id: str,
    title: str,
    icon: str,
    description: str,
    *,
    href: str | None = None,
    coming_soon: bool = False,
):
    """Build a settings hub card.

    Args:
        card_id: Unique identifier for the card (used in the pattern-matching id).
        title: Card title text.
        icon: Font Awesome icon class (e.g. ``"fa-solid fa-sliders"``).
        description: Short description displayed below the title.
        href: If provided, the card is clickable and navigates to this path.
        coming_soon: If True, a "Coming soon" badge is shown in the top-right.

    Returns:
        A Dash html.Div representing the card.
    """
    is_clickable = href is not None

    children: list = [
        # Top row: icon + title + optional coming-soon badge
        html.Div(
            [
                html.I(
                    className=icon,
                    style={
                        "fontSize": "20px",
                        "color": COLOR_NAVY,
                        "marginRight": SPACING_XSMALL,
                    },
                ),
                html.Div(
                    title,
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": FONT_SIZE_MEDIUM,
                        "fontWeight": FONT_WEIGHT_MEDIUM,
                        "color": COLOR_CHARCOAL_MEDIUM,
                        "flex": 1,
                    },
                ),
            ]
            + (
                [
                    dbc.Badge(
                        "Coming soon",
                        color="secondary",
                        className="ms-2",
                        style={"fontSize": FONT_SIZE_XTINY},
                    ),
                ]
                if coming_soon
                else []
            ),
            style={"display": "flex", "alignItems": "center"},
        ),
        # Description
        html.Div(
            description,
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_SMALL,
                "color": COLOR_GRAY_MEDIUM,
                "marginTop": SPACING_XSMALL,
                "lineHeight": "1.5",
            },
        ),
    ]

    card_props: dict = {
        "id": {"type": "settings-card", "card_id": card_id},
        "className": "settings-card",
        "style": {
            "padding": SPACING_SMALL,
            "backgroundColor": COLOR_BACKGROUND_LIGHT,
            "border": f"1px solid {COLOR_BORDER}",
            "borderRadius": "2px",
            "userSelect": "none",
        },
    }

    if is_clickable:
        card_props["n_clicks"] = 0
        card_props["style"]["cursor"] = "pointer"
    else:
        card_props["style"]["cursor"] = "default"

    return html.Div(children, **card_props)