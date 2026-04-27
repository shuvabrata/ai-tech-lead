from dash import html
import dash_bootstrap_components as dbc

from app.dash_app.components.common import (
    create_feature_card,
    create_diamond_icon
)
from app.dash_app.styles import (
    CARD_CONTAINER_STYLE,
    FONT_SANS,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    COLOR_GRAY_DARK,
    COLOR_GRAY_MEDIUM,
    SPACING_SMALL,
    SPACING_MEDIUM,
    SPACING_LARGE,
    COLOR_BACKGROUND_WHITE,
    COLOR_BORDER
)


def get_layout():
    """Return the people page layout with Executive Dashboard aesthetic"""
    return html.Div([
        # Main content container
        html.Div([
            # Placeholder message section
            html.Div([
                html.Div(
                    [create_diamond_icon()],
                    style={
                        "fontSize": "32px",
                        "marginBottom": SPACING_SMALL,
                        "textAlign": "center"
                    }
                ),
                html.Div(
                    "Team directory integration pending",
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": FONT_SIZE_LARGE,
                        "color": COLOR_GRAY_DARK,
                        "marginBottom": SPACING_MEDIUM,
                        "textAlign": "center",
                        "fontWeight": "400"
                    }
                ),
                html.Div(
                    "This module will provide comprehensive personnel oversight, including:",
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": FONT_SIZE_MEDIUM,
                        "color": COLOR_GRAY_MEDIUM,
                        "marginBottom": SPACING_SMALL,
                        "lineHeight": "1.7"
                    }
                ),
            ], style={
                "maxWidth": "640px",
                "marginLeft": "auto",
                "marginRight": "auto",
                "marginBottom": SPACING_LARGE,
                "padding": f"{SPACING_LARGE} {SPACING_LARGE}",
                "backgroundColor": COLOR_BACKGROUND_WHITE,
                "border": f"1px solid {COLOR_BORDER}",
                "borderRadius": "2px"
            }),
            
            # Feature grid
            dbc.Row([
                dbc.Col([
                    create_feature_card(
                        "Personnel Profiles",
                        "Detailed team member information, roles, and expertise areas"
                    )
                ], md=6, className="mb-3"),
                
                dbc.Col([
                    create_feature_card(
                        "Organizational Structure",
                        "Reporting hierarchies, department assignments, and team composition"
                    )
                ], md=6, className="mb-3"),
                
                dbc.Col([
                    create_feature_card(
                        "Contact Directory",
                        "Email addresses, communication channels, and preferred contact methods"
                    )
                ], md=6, className="mb-3"),
                
                dbc.Col([
                    create_feature_card(
                        "Availability & Capacity",
                        "Current workload, availability status, and resource allocation metrics"
                    )
                ], md=6, className="mb-3"),
            ])
        ], style=CARD_CONTAINER_STYLE)
    ], className="mt-3")
