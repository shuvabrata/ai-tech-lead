"""
Common Reusable Components for Executive Dashboard

This module provides factory functions for creating consistent UI components
across all pages of the Work Behavior Analytics AI application.

Usage:
    from app.dash_app.components.common import create_page_header, create_feature_card
    
    layout = html.Div([
        create_page_header("My Page Title"),
        create_feature_card("Feature Title", "Feature description...")
    ])
"""

from dash import html
import dash_bootstrap_components as dbc

from app.dash_app.styles import (
    # Style patterns
    PAGE_HEADER_STYLE,
    CARD_CONTAINER_STYLE,
    FEATURE_CARD_STYLE,
    FEATURE_CARD_TITLE_STYLE,
    FEATURE_CARD_DESCRIPTION_STYLE,
    PLACEHOLDER_ICON_STYLE,
    PLACEHOLDER_MESSAGE_STYLE,
    # Colors
    COLOR_NAVY,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_MEDIUM,
    COLOR_BORDER,
    # Typography
    FONT_SANS,
    FONT_SIZE_XSMALL,
    # Spacing
    SPACING_XSMALL,
    SPACING_SMALL,
    SPACING_MEDIUM,
    SPACING_XXSMALL
)


def create_page_header(text: str) -> html.Div:
    """
    Create a consistent page header with Executive Dashboard styling.
    
    Args:
        text: The header text to display
        
    Returns:
        html.Div: A styled page header component
        
    Example:
        create_page_header("Strategic Analysis & Advisory")
    """
    return html.Div(text, style=PAGE_HEADER_STYLE)


def create_feature_card(title: str, description: str) -> html.Div:
    """
    Create a feature card with title and description.
    
    Args:
        title: The feature title
        description: The feature description text
        
    Returns:
        html.Div: A styled feature card component
        
    Example:
        create_feature_card(
            "Personnel Profiles",
            "Detailed team member information, roles, and expertise areas"
        )
    """
    return html.Div([
        html.Div(title, style=FEATURE_CARD_TITLE_STYLE),
        html.Div(description, style=FEATURE_CARD_DESCRIPTION_STYLE)
    ], style=FEATURE_CARD_STYLE)


def create_placeholder_section(message: str, features: list, icon: str = "📋") -> html.Div:
    """
    Create a placeholder section with icon, message, and feature cards.
    
    Args:
        message: The placeholder message to display
        features: List of (title, description) tuples for feature cards
        icon: Optional icon to display (default: "📋")
        
    Returns:
        html.Div: A complete placeholder section
        
    Example:
        create_placeholder_section(
            message="Team directory integration pending",
            features=[
                ("Personnel Profiles", "Detailed team member information..."),
                ("Contact Directory", "Email addresses and communication...")
            ]
        )
    """
    # Create feature cards in a 2-column grid
    feature_cols = []
    for title, description in features:
        feature_cols.append(
            dbc.Col([
                create_feature_card(title, description)
            ], md=6)
        )
    
    return html.Div([
        # Icon
        html.Div(icon, style=PLACEHOLDER_ICON_STYLE),
        
        # Message
        html.Div(message, style=PLACEHOLDER_MESSAGE_STYLE),
        
        # Feature cards
        html.Div([
            dbc.Row(feature_cols)
        ], style=CARD_CONTAINER_STYLE)
    ])


def create_diamond_icon(color: str | None = None) -> html.Span:
    """
    Create a diamond icon (◆) for visual accents.
    
    Args:
        color: The color of the diamond (default: theme accent)
        
    Returns:
        html.Span: A styled diamond icon
        
    Example:
        create_diamond_icon()
        create_diamond_icon(COLOR_GRAY_MEDIUM)
    """
    resolved_color = color or COLOR_NAVY

    return html.Span(
        "◆",
        style={
            "color": resolved_color,
            "fontSize": FONT_SIZE_XSMALL,
            "marginRight": SPACING_XXSMALL
        }
    )


def create_empty_state(message: str, icon: str = "📭") -> html.Div:
    """
    Create an empty state display for when there's no data.
    
    Args:
        message: The message to display
        icon: Optional icon to display (default: "📭")
        
    Returns:
        html.Div: A styled empty state component
        
    Example:
        create_empty_state("No messages yet. Start a conversation!")
    """
    return html.Div([
        html.Div(icon, style=PLACEHOLDER_ICON_STYLE),
        html.Div(message, style=PLACEHOLDER_MESSAGE_STYLE)
    ], style={
        "padding": SPACING_MEDIUM,
        "textAlign": "center"
    })


def create_info_card(title: str, content: str, accent_color: str | None = None) -> html.Div:
    """
    Create an informational card with custom accent color.
    
    Args:
        title: The card title
        content: The card content text
        accent_color: Border accent color (default: theme accent)
        
    Returns:
        html.Div: A styled info card component
        
    Example:
        create_info_card(
            "Project Status",
            "All systems operational",
            COLOR_SUCCESS
        )
    """
    resolved_accent_color = accent_color or COLOR_NAVY

    card_style = {
        **FEATURE_CARD_STYLE,
        "borderLeft": f"3px solid {resolved_accent_color}"
    }
    
    return html.Div([
        html.Div(title, style=FEATURE_CARD_TITLE_STYLE),
        html.Div(content, style=FEATURE_CARD_DESCRIPTION_STYLE)
    ], style=card_style)


def create_section_divider(text: str = None) -> html.Div:
    """
    Create a section divider with optional text.
    
    Args:
        text: Optional text to display in the divider
        
    Returns:
        html.Div: A styled section divider
        
    Example:
        create_section_divider()
        create_section_divider("Analysis Results")
    """
    if text:
        return html.Div(
            text,
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_XSMALL,
                "color": COLOR_GRAY_MEDIUM,
                "textTransform": "uppercase",
                "letterSpacing": "1px",
                "borderTop": f"1px solid {COLOR_BORDER}",
                "paddingTop": SPACING_XSMALL,
                "marginTop": SPACING_MEDIUM,
                "marginBottom": SPACING_SMALL
            }
        )
    else:
        return html.Hr(style={
            "borderTop": f"1px solid {COLOR_BORDER}",
            "marginTop": SPACING_MEDIUM,
            "marginBottom": SPACING_MEDIUM
        })


def create_stat_card(label: str, value: str, subtitle: str = None) -> html.Div:
    """
    Create a statistics card with label, value, and optional subtitle.
    
    Args:
        label: The stat label
        value: The stat value to display prominently
        subtitle: Optional subtitle text
        
    Returns:
        html.Div: A styled stat card component
        
    Example:
        create_stat_card("Active Tasks", "24", "↑ 12% from last week")
    """
    components = [
        html.Div(
            label,
            style={
                "fontFamily": FONT_SANS,
                "fontSize": FONT_SIZE_XSMALL,
                "color": COLOR_GRAY_MEDIUM,
                "textTransform": "uppercase",
                "letterSpacing": "1px",
                "marginBottom": SPACING_XXSMALL
            }
        ),
        html.Div(
            value,
            style={
                "fontFamily": FONT_SANS,
                "fontSize": "32px",
                "fontWeight": "700",
                "color": COLOR_CHARCOAL_MEDIUM,
                "marginBottom": SPACING_XXSMALL
            }
        )
    ]
    
    if subtitle:
        components.append(
            html.Div(
                subtitle,
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": FONT_SIZE_XSMALL,
                    "color": COLOR_GRAY_MEDIUM,
                    "fontStyle": "italic"
                }
            )
        )
    
    return html.Div(
        components,
        style={
            **FEATURE_CARD_STYLE,
            "textAlign": "center"
        }
    )
