"""
Executive Dashboard Design System

This module provides centralized design tokens for the AI Tech Lead application.
All color values, typography settings, spacing, and common style patterns are
defined here as the single source of truth for the Executive Dashboard aesthetic.

Usage:
    from app.dash_app.styles import COLOR_NAVY, FONT_SANS, PAGE_HEADER_STYLE
    
    html.Div("My Header", style=PAGE_HEADER_STYLE)
"""

# =============================================================================
# TYPOGRAPHY
# =============================================================================

# Font Families
FONT_SERIF = "'Cormorant Garamond', serif"
FONT_SANS = "'Inter', sans-serif"

# Font Sizes
FONT_SIZE_XLARGE = "42px"
FONT_SIZE_LARGE = "15px"
FONT_SIZE_MEDIUM = "14px"
FONT_SIZE_SMALL = "13px"
FONT_SIZE_XSMALL = "12px"

# Font Weights
FONT_WEIGHT_NORMAL = "400"
FONT_WEIGHT_MEDIUM = "500"
FONT_WEIGHT_SEMIBOLD = "600"
FONT_WEIGHT_BOLD = "700"

# =============================================================================
# COLORS - Executive Dashboard Palette
# =============================================================================

# Primary Colors
COLOR_NAVY = "#2c5282"
COLOR_NAVY_DARK = "#1e3a5f"
COLOR_NAVY_HOVER = "#234164"

# Text Colors
COLOR_CHARCOAL = "#1a202c"
COLOR_CHARCOAL_MEDIUM = "#2d3748"
COLOR_GRAY_DARK = "#4a5568"
COLOR_GRAY_MEDIUM = "#718096"
COLOR_GRAY_LIGHT = "#a0aec0"
COLOR_GRAY_LIGHTER = "#cbd5e0"

# Background Colors
COLOR_BACKGROUND_WHITE = "#ffffff"
COLOR_BACKGROUND_LIGHT = "#f7fafc"
COLOR_SURFACE_ACTIVE = "#edf2f7"

# Border Colors
COLOR_BORDER = "#e2e8f0"
COLOR_BORDER_LIGHT = "#e2e8f0"

# Utility Colors
COLOR_SUCCESS = "#48bb78"
COLOR_WARNING = "#ed8936"
COLOR_ERROR = "#f56565"
COLOR_INFO = "#4299e1"

# =============================================================================
# SPACING
# =============================================================================

SPACING_XXXSMALL = "4px"
SPACING_XXSMALL = "8px"
SPACING_XSMALL = "12px"
SPACING_SMALL = "16px"
SPACING_MEDIUM = "24px"
SPACING_LARGE = "32px"
SPACING_XLARGE = "40px"
SPACING_XXLARGE = "48px"

# =============================================================================
# COMMON STYLE PATTERNS
# =============================================================================

# Page Headers
PAGE_HEADER_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_SMALL,
    "color": COLOR_GRAY_MEDIUM,
    "letterSpacing": "1.5px",
    "textTransform": "uppercase",
    "fontWeight": FONT_WEIGHT_MEDIUM,
    "borderBottom": f"1px solid {COLOR_BORDER}",
    "paddingBottom": SPACING_XSMALL,
    "marginBottom": SPACING_SMALL
}

# Card Containers
CARD_CONTAINER_STYLE = {
    "backgroundColor": COLOR_BACKGROUND_WHITE,
    "padding": SPACING_MEDIUM,
    "borderRadius": "2px"
}

# Feature Cards
FEATURE_CARD_STYLE = {
    "padding": SPACING_MEDIUM,
    "backgroundColor": COLOR_BACKGROUND_LIGHT,
    "border": f"1px solid {COLOR_BORDER}",
    "borderLeft": f"3px solid {COLOR_NAVY}",
    "borderRadius": "2px",
    "marginBottom": SPACING_SMALL
}

FEATURE_CARD_TITLE_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_MEDIUM,
    "fontWeight": FONT_WEIGHT_SEMIBOLD,
    "color": COLOR_CHARCOAL_MEDIUM,
    "marginBottom": SPACING_XXSMALL,
    "textTransform": "uppercase",
    "letterSpacing": "0.5px"
}

FEATURE_CARD_DESCRIPTION_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_SMALL,
    "color": COLOR_GRAY_MEDIUM,
    "lineHeight": "1.6"
}

# Placeholder Sections
PLACEHOLDER_ICON_STYLE = {
    "fontSize": "48px",
    "color": COLOR_GRAY_LIGHT,
    "marginBottom": SPACING_SMALL,
    "textAlign": "center"
}

PLACEHOLDER_MESSAGE_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_MEDIUM,
    "color": COLOR_GRAY_MEDIUM,
    "textAlign": "center",
    "marginBottom": SPACING_MEDIUM,
    "fontStyle": "italic"
}

# Chat Message Styles
CHAT_MESSAGE_USER_STYLE = {
    "backgroundColor": COLOR_NAVY,
    "color": COLOR_BACKGROUND_WHITE,
    "padding": SPACING_SMALL,
    "borderRadius": "2px",
    "marginBottom": SPACING_XSMALL,
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_SMALL,
    "lineHeight": "1.6"
}

CHAT_MESSAGE_AI_CONTAINER_STYLE = {
    "backgroundColor": COLOR_BACKGROUND_LIGHT,
    "padding": SPACING_SMALL,
    "borderRadius": "2px",
    "marginBottom": SPACING_XSMALL,
    "borderLeft": f"3px solid {COLOR_NAVY}"
}

CHAT_MESSAGE_AI_HEADER_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_XSMALL,
    "color": COLOR_GRAY_MEDIUM,
    "marginBottom": SPACING_XXSMALL,
    "display": "flex",
    "alignItems": "center",
    "gap": SPACING_XXSMALL
}

CHAT_MESSAGE_AI_CONTENT_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_SMALL,
    "color": COLOR_CHARCOAL_MEDIUM,
    "lineHeight": "1.7"
}

# Input Styles
INPUT_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_SMALL,
    "padding": SPACING_XSMALL,
    "border": f"1px solid {COLOR_BORDER}",
    "borderRadius": "2px",
    "width": "100%"
}

INPUT_FOCUS_STYLE = {
    **INPUT_STYLE,
    "borderColor": COLOR_NAVY,
    "outline": "none",
    "boxShadow": "0 0 0 3px rgba(44, 82, 130, 0.1)"
}

# Button Styles
BUTTON_PRIMARY_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_SMALL,
    "fontWeight": FONT_WEIGHT_MEDIUM,
    "backgroundColor": COLOR_NAVY,
    "color": COLOR_BACKGROUND_WHITE,
    "border": "none",
    "borderRadius": "2px",
    "padding": f"{SPACING_XSMALL} {SPACING_MEDIUM}",
    "cursor": "pointer",
    "textTransform": "uppercase",
    "letterSpacing": "0.5px"
}

BUTTON_SECONDARY_STYLE = {
    **BUTTON_PRIMARY_STYLE,
    "backgroundColor": COLOR_BACKGROUND_WHITE,
    "color": COLOR_NAVY,
    "border": f"1px solid {COLOR_NAVY}"
}

# Graph Controls
GRAPH_CONTROL_LABEL_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_SMALL,
    "fontWeight": FONT_WEIGHT_MEDIUM,
    "color": COLOR_CHARCOAL_MEDIUM,
    "marginBottom": SPACING_XXSMALL,
    "textTransform": "uppercase",
    "letterSpacing": "0.5px"
}

GRAPH_CONTAINER_STYLE = {
    "backgroundColor": COLOR_BACKGROUND_WHITE,
    "border": f"1px solid {COLOR_BORDER}",
    "borderRadius": "2px",
    "padding": SPACING_XSMALL
}

# Navigation & Layout
SIDEBAR_STYLE = {
    "backgroundColor": COLOR_BACKGROUND_WHITE,
    "borderRight": f"1px solid {COLOR_BORDER}",
    "padding": f"{SPACING_MEDIUM} 0"
}

NAVBAR_BRAND_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_MEDIUM,
    "marginBottom": "0",
    "fontWeight": FONT_WEIGHT_SEMIBOLD,
    "padding": "0",
    "color": COLOR_CHARCOAL_MEDIUM,
    "letterSpacing": "0.5px",
    "textTransform": "uppercase"
}

TOPBAR_STYLE = {
    "minHeight": "auto",
    "height": "44px",
    "padding": "0",
    "borderBottom": f"1px solid {COLOR_BORDER}",
    "boxShadow": "0 1px 2px rgba(0,0,0,0.04)"
}

TOPBAR_CONTAINER_STYLE = {
    "padding": "8px 16px"
}

TOGGLE_BUTTON_STYLE = {
    "fontSize": "16px",
    "fontWeight": "normal",
    "padding": "4px 10px",
    "lineHeight": "1",
    "borderColor": COLOR_GRAY_LIGHTER,
    "color": COLOR_GRAY_DARK,
    "backgroundColor": "transparent"
}

DROPDOWN_MENU_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_XSMALL
}

SIDEBAR_COL_STYLE = {
    "minWidth": "180px",
    "maxWidth": "180px"
}

# =============================================================================
# GRAPH PAGE COMPONENTS
# =============================================================================

GRAPH_SECTION_CONTAINER_STYLE = {
    "backgroundColor": COLOR_BACKGROUND_WHITE,
    "borderRadius": "2px",
    "border": f"1px solid {COLOR_BORDER}",
    "padding": SPACING_XSMALL,
    "marginBottom": SPACING_XSMALL
}

GRAPH_SECTION_TITLE_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_XSMALL,
    "fontWeight": "600",
    "color": COLOR_CHARCOAL_MEDIUM,
    "marginBottom": SPACING_XSMALL,
    "textTransform": "uppercase",
    "letterSpacing": "0.5px"
}

GRAPH_QUERY_TEXTAREA_STYLE = {
    "fontFamily": FONT_SANS,
    "height": "90px",
    "borderRadius": "2px",
    "border": f"1px solid {COLOR_GRAY_LIGHTER}",
    "padding": f"{SPACING_XSMALL} {SPACING_SMALL}",
    "fontSize": FONT_SIZE_SMALL,
    "resize": "vertical",
    "transition": "border-color 0.2s",
    "backgroundColor": COLOR_BACKGROUND_WHITE,
    "color": COLOR_CHARCOAL_MEDIUM
}

GRAPH_EXECUTE_BUTTON_STYLE = {
    "fontFamily": FONT_SANS,
    "borderRadius": "2px",
    "fontWeight": "500",
    "fontSize": FONT_SIZE_SMALL,
    "height": "90px",
    "width": "100%",
    "backgroundColor": COLOR_NAVY,
    "border": "none",
    "letterSpacing": "0.5px",
    "textTransform": "uppercase",
    "transition": "all 0.2s ease"
}

GRAPH_HELPER_TEXT_STYLE = {
    "fontFamily": FONT_SANS,
    "fontSize": "11px",
    "color": COLOR_GRAY_LIGHT,
    "letterSpacing": "0.3px"
}

GRAPH_QUERY_SECTION_CONTAINER_STYLE = {
    "backgroundColor": COLOR_BACKGROUND_LIGHT,
    "borderRadius": "2px",
    "border": f"1px solid {COLOR_BORDER}",
    "padding": SPACING_SMALL,
    "marginTop": SPACING_XSMALL
}

GRAPH_CYTOSCAPE_STYLE = {
    "width": "100%",
    "height": "75vh",
    "backgroundColor": "#fafafa",
    "borderRadius": "4px"
}

GRAPH_EMPTY_STATE_ICON_STYLE = {
    "fontFamily": FONT_SERIF,
    "fontSize": "28px",
    "color": COLOR_GRAY_LIGHTER,
    "marginBottom": SPACING_XSMALL
}

GRAPH_EMPTY_STATE_TEXT_STYLE = {
    "fontFamily": FONT_SANS,
    "color": COLOR_GRAY_LIGHT,
    "fontSize": FONT_SIZE_SMALL,
    "lineHeight": "1.6"
}

GRAPH_DETAILS_PANEL_STYLE = {
    "backgroundColor": "#f8f9fa",
    "borderRadius": "4px",
    "border": "1px solid #dee2e6",
    "padding": SPACING_XXSMALL,
    "height": "calc(75vh + 40px)",
    "overflowY": "auto"
}

GRAPH_DETAILS_PANEL_ICON_STYLE = {
    "color": "#adb5bd"
}

# Graph page constant (used in dcc.Loading component)
GRAPH_LOADING_COLOR = COLOR_NAVY

# =============================================================================
# LAYOUT UTILITIES
# =============================================================================

def merge_styles(*styles):
    """
    Merge multiple style dictionaries together.
    Later styles override earlier ones.
    
    Args:
        *styles: Variable number of style dictionaries
        
    Returns:
        dict: Merged style dictionary
        
    Example:
        combined = merge_styles(BASE_STYLE, {"color": "red"})
    """
    result = {}
    for style in styles:
        if style:
            result.update(style)
    return result
