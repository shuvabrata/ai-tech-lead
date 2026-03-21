"""
Executive Dashboard Design System

This module provides centralized design tokens for the Work Behavior Analytics AI application.
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
FONT_SIZE_TINY = "11px"
FONT_SIZE_XTINY = "10px"
FONT_SIZE_XXSMALL = "9px"

# Font Weights
FONT_WEIGHT_NORMAL = "400"
FONT_WEIGHT_MEDIUM = "500"
FONT_WEIGHT_SEMIBOLD = "600"
FONT_WEIGHT_BOLD = "700"

# =============================================================================
# COLORS - Theme Tokens
# =============================================================================

ACTIVE_THEME = "executive-light"

# Semantic token registry.
# Keeping all existing exported COLOR_* constants below preserves current imports
# while making it straightforward to add additional themes later.
THEME_TOKENS = {
    "executive-light": {
        # Brand / accent
        "brand.primary": "#2c5282",
        "brand.primary.dark": "#1e3a5f",
        "brand.primary.hover": "#234164",

        # Text
        "text.primary": "#1a202c",
        "text.secondary": "#2d3748",
        "text.tertiary": "#4a5568",
        "text.muted": "#718096",
        "text.subtle": "#a0aec0",
        "text.disabled": "#cbd5e0",

        # Surfaces
        "surface.base": "#ffffff",
        "surface.subtle": "#f7fafc",
        "surface.active": "#edf2f7",
        "surface.pale": "#f8f9fa",

        # Borders
        "border.default": "#e2e8f0",
        "border.light": "#e2e8f0",
        "border.medium": "#dee2e6",
        "border.context-menu": "#ccc",

        # Utility
        "utility.success": "#48bb78",
        "utility.warning": "#ed8936",
        "utility.error": "#f56565",
        "utility.info": "#4299e1",
        "utility.destructive": "#dc3545",
        "utility.warning.dark": "#ffc107",
        "utility.success.dark": "#28a745",

        # Extended UI
        "ui.text.dark": "#212529",
        "ui.text.muted": "#6c757d",
        "ui.text.secondary": "#495057",
        "ui.code.background": "#e9ecef",
        "ui.details.icon": "#adb5bd",
        "ui.graph.canvas": "#fafafa",
        "ui.shadow.light": "rgba(0,0,0,0.2)",
        "ui.focus.ring": "rgba(44, 82, 130, 0.1)",
        "ui.validation.code.background": "rgba(255,255,255,0.3)",
        "ui.topbar.shadow": "rgba(0,0,0,0.04)",

        # Graph palette tokens (Cytoscape)
        "graph.node.default": "#B8B8B8",
        "graph.node.default.border": "#9E9E9E",
        "graph.node.project": "#AEC6CF",
        "graph.node.project.border": "#8FA8B5",
        "graph.node.person": "#C5B4E3",
        "graph.node.person.border": "#A798C7",
        "graph.node.branch": "#B5E7E3",
        "graph.node.branch.border": "#96C9C5",
        "graph.node.epic": "#F4C2B0",
        "graph.node.epic.border": "#D9A892",
        "graph.node.issue": "#F5E6D3",
        "graph.node.issue.border": "#D9C8B5",
        "graph.node.repository": "#C8D5B9",
        "graph.node.repository.border": "#AAB89B",
        "graph.edge.default": "#C0C0C0",
        "graph.selection": "#424242",
    },
    "executive-dark": {
        # Brand / accent (slightly brighter for dark surfaces)
        "brand.primary": "#5f86b4",
        "brand.primary.dark": "#4d739f",
        "brand.primary.hover": "#6b93c3",

        # Text
        "text.primary": "#e6edf3",
        "text.secondary": "#ced8e3",
        "text.tertiary": "#a9b6c5",
        "text.muted": "#8f9fb1",
        "text.subtle": "#78889b",
        "text.disabled": "#5f6f82",

        # Surfaces (soft dark, not pure black)
        "surface.base": "#1f262f",
        "surface.subtle": "#252f3a",
        "surface.active": "#2f3b49",
        "surface.pale": "#2a3440",

        # Borders
        "border.default": "#3a4653",
        "border.light": "#445262",
        "border.medium": "#4c5968",
        "border.context-menu": "#566474",

        # Utility
        "utility.success": "#57b983",
        "utility.warning": "#d6a564",
        "utility.error": "#db7f7f",
        "utility.info": "#62a6d8",
        "utility.destructive": "#d97b7b",
        "utility.warning.dark": "#d9b26d",
        "utility.success.dark": "#5eb88d",

        # Extended UI
        "ui.text.dark": "#e6edf3",
        "ui.text.muted": "#98a8bb",
        "ui.text.secondary": "#bdc9d7",
        "ui.code.background": "#323e4b",
        "ui.details.icon": "#8ea0b3",
        "ui.graph.canvas": "#222b35",
        "ui.shadow.light": "rgba(0,0,0,0.35)",
        "ui.focus.ring": "rgba(95, 134, 180, 0.28)",
        "ui.validation.code.background": "rgba(255,255,255,0.08)",
        "ui.topbar.shadow": "rgba(0,0,0,0.28)",

        # Graph palette tokens (muted, professional on dark canvas)
        "graph.node.default": "#7f8fa3",
        "graph.node.default.border": "#96a4b6",
        "graph.node.project": "#6f8fb1",
        "graph.node.project.border": "#89a5c2",
        "graph.node.person": "#8b7eab",
        "graph.node.person.border": "#a193bf",
        "graph.node.branch": "#6b9ea1",
        "graph.node.branch.border": "#83b3b6",
        "graph.node.epic": "#b18676",
        "graph.node.epic.border": "#c49a8b",
        "graph.node.issue": "#b6a58a",
        "graph.node.issue.border": "#cabaa1",
        "graph.node.repository": "#7e9a7b",
        "graph.node.repository.border": "#97b092",
        "graph.edge.default": "#8c9aab",
        "graph.selection": "#d5deea",
    }
}


def get_theme_tokens(theme_name: str = ACTIVE_THEME) -> dict:
    """Return semantic tokens for the requested theme."""
    if theme_name not in THEME_TOKENS:
        available = ", ".join(sorted(THEME_TOKENS.keys()))
        raise ValueError(f"Unknown theme '{theme_name}'. Available themes: {available}")
    return THEME_TOKENS[theme_name]


TOKENS = get_theme_tokens()


def _token(name: str) -> str:
    """Fetch a token from the active theme and fail fast if missing."""
    try:
        return TOKENS[name]
    except KeyError as exc:
        raise KeyError(f"Theme token not found: {name}") from exc


# Legacy color exports backed by CSS variables for runtime theme switching.
# Theme hex values remain available through get_theme_tokens(...).

# Primary Colors
COLOR_NAVY = "var(--color-navy)"
COLOR_NAVY_DARK = "var(--color-navy-dark)"
COLOR_NAVY_HOVER = "var(--color-navy-hover)"

# Text Colors
COLOR_CHARCOAL = "var(--color-charcoal)"
COLOR_CHARCOAL_MEDIUM = "var(--color-charcoal-medium)"
COLOR_GRAY_DARK = "var(--color-gray-dark)"
COLOR_GRAY_MEDIUM = "var(--color-gray-medium)"
COLOR_GRAY_LIGHT = "var(--color-gray-light)"
COLOR_GRAY_LIGHTER = "var(--color-gray-lighter)"

# Background Colors
COLOR_BACKGROUND_WHITE = "var(--color-background-white)"
COLOR_BACKGROUND_LIGHT = "var(--color-background-light)"
COLOR_SURFACE_ACTIVE = "var(--color-surface-active)"

# Border Colors
COLOR_BORDER = "var(--color-border)"
COLOR_BORDER_LIGHT = "var(--color-border-light)"

# Utility Colors
COLOR_SUCCESS = "var(--color-success)"
COLOR_WARNING = "var(--color-warning)"
COLOR_ERROR = "var(--color-error)"
COLOR_INFO = "var(--color-info)"

# Extended Colors (Graph UI Components)
COLOR_TEXT_DARK = "var(--color-text-dark)"
COLOR_TEXT_MUTED = "var(--color-text-muted)"
COLOR_TEXT_SECONDARY = "var(--color-text-secondary)"
COLOR_BACKGROUND_PALE = "var(--color-background-pale)"
COLOR_BORDER_GRAY = "var(--color-border-gray)"
COLOR_CODE_BACKGROUND = "var(--color-code-background)"
COLOR_SHADOW_LIGHT = "var(--color-shadow-light)"
COLOR_CONTEXT_MENU_BORDER = "var(--color-context-menu-border)"
COLOR_DESTRUCTIVE = "var(--color-destructive)"
COLOR_WARNING_DARK = "var(--color-warning-dark)"
COLOR_SUCCESS_DARK = "var(--color-success-dark)"

# Graph palette tokens (Cytoscape)
COLOR_GRAPH_NODE_DEFAULT = "var(--color-graph-node-default)"
COLOR_GRAPH_NODE_DEFAULT_BORDER = "var(--color-graph-node-default-border)"
COLOR_GRAPH_NODE_PROJECT = "var(--color-graph-node-project)"
COLOR_GRAPH_NODE_PROJECT_BORDER = "var(--color-graph-node-project-border)"
COLOR_GRAPH_NODE_PERSON = "var(--color-graph-node-person)"
COLOR_GRAPH_NODE_PERSON_BORDER = "var(--color-graph-node-person-border)"
COLOR_GRAPH_NODE_BRANCH = "var(--color-graph-node-branch)"
COLOR_GRAPH_NODE_BRANCH_BORDER = "var(--color-graph-node-branch-border)"
COLOR_GRAPH_NODE_EPIC = "var(--color-graph-node-epic)"
COLOR_GRAPH_NODE_EPIC_BORDER = "var(--color-graph-node-epic-border)"
COLOR_GRAPH_NODE_ISSUE = "var(--color-graph-node-issue)"
COLOR_GRAPH_NODE_ISSUE_BORDER = "var(--color-graph-node-issue-border)"
COLOR_GRAPH_NODE_REPOSITORY = "var(--color-graph-node-repository)"
COLOR_GRAPH_NODE_REPOSITORY_BORDER = "var(--color-graph-node-repository-border)"
COLOR_GRAPH_EDGE_DEFAULT = "var(--color-graph-edge-default)"
COLOR_GRAPH_SELECTION = "var(--color-graph-selection)"

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
    "boxShadow": "0 0 0 3px var(--color-focus-ring)"
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
    "boxShadow": "0 1px 2px var(--color-topbar-shadow)",
    "backgroundColor": COLOR_BACKGROUND_WHITE
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
    "backgroundColor": "var(--color-graph-canvas)",
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
    "backgroundColor": COLOR_BACKGROUND_PALE,
    "borderRadius": "4px",
    "border": f"1px solid {COLOR_BORDER_GRAY}",
    "padding": SPACING_XXSMALL,
    "height": "calc(75vh + 40px)",
    "overflowY": "auto"
}

GRAPH_DETAILS_PANEL_ICON_STYLE = {
    "color": "var(--color-details-icon)"
}

GRAPH_NODE_HOVER_TOOLTIP_STYLE = {
    "display": "none",
    "position": "fixed",
    "zIndex": 9999,
    "pointerEvents": "none",
    "backgroundColor": COLOR_BACKGROUND_WHITE,
    "border": f"1px solid {COLOR_BORDER}",
    "borderRadius": "4px",
    "padding": f"{SPACING_XXXSMALL} {SPACING_XXSMALL}",
    "fontFamily": FONT_SANS,
    "fontSize": FONT_SIZE_XSMALL,
    "color": COLOR_CHARCOAL_MEDIUM,
    "maxWidth": "320px",
    "boxShadow": f"0 2px 8px {COLOR_SHADOW_LIGHT}",
    "whiteSpace": "normal",
    "wordBreak": "break-word",
}

# Graph page constant (used in dcc.Loading component)
GRAPH_LOADING_COLOR = COLOR_NAVY

# =============================================================================
# GRAPH UI COMPONENTS (Callbacks, Menus, Details)
# =============================================================================

# Context Menu Styles
CONTEXT_MENU_CONTAINER_STYLE = {
    "position": "fixed",
    "display": "none",
    "backgroundColor": COLOR_BACKGROUND_WHITE,
    "border": f"1px solid {COLOR_CONTEXT_MENU_BORDER}",
    "borderRadius": "4px",
    "boxShadow": f"2px 2px 8px {COLOR_SHADOW_LIGHT}",
    "zIndex": "9999",
    "minWidth": "180px",
    "padding": "4px 0"
}

CONTEXT_MENU_ITEM_STYLE = {
    "padding": "8px 16px",
    "cursor": "pointer",
    "fontSize": FONT_SIZE_SMALL,
    "color": COLOR_CHARCOAL_MEDIUM
}

CONTEXT_MENU_DIVIDER_STYLE = {
    "margin": "4px 0",
    "borderTop": f"1px solid {COLOR_BORDER}"
}

CONTEXT_MENU_DESTRUCTIVE_STYLE = {
    "padding": "8px 16px",
    "cursor": "pointer",
    "fontSize": FONT_SIZE_SMALL,
    "color": COLOR_DESTRUCTIVE
}

# Validation Message Styles
VALIDATION_ALERT_STYLE = {
    "fontSize": FONT_SIZE_SMALL
}

VALIDATION_CODE_STYLE = {
    "fontSize": FONT_SIZE_XSMALL,
    "backgroundColor": "var(--color-validation-code-background)",
    "padding": "2px 6px"
}

# Details Panel Styles
DETAILS_LABEL_STYLE = {
    "color": COLOR_TEXT_MUTED,
    "fontSize": FONT_SIZE_SMALL
}

DETAILS_VALUE_STYLE = {
    "color": COLOR_TEXT_DARK,
    "fontSize": FONT_SIZE_SMALL
}

DETAILS_HEADING_STYLE = {
    "fontWeight": FONT_WEIGHT_SEMIBOLD,
    "color": COLOR_CHARCOAL_MEDIUM
}

DETAILS_SUBHEADING_STYLE = {
    "fontSize": FONT_SIZE_MEDIUM,
    "fontWeight": FONT_WEIGHT_SEMIBOLD,
    "color": COLOR_TEXT_SECONDARY,
    "marginBottom": SPACING_XSMALL
}

DETAILS_CODE_STYLE = {
    "fontSize": FONT_SIZE_TINY,
    "backgroundColor": COLOR_CODE_BACKGROUND,
    "padding": "2px 6px",
    "borderRadius": "3px"
}

DETAILS_MUTED_TEXT_STYLE = {
    "fontSize": FONT_SIZE_SMALL,
    "fontStyle": "italic"
}

DETAILS_SEPARATOR_STYLE = {
    "margin": "12px 0"
}

# Property Formatter Styles
PROPERTY_COMPLEX_VALUE_STYLE = {
    "fontSize": FONT_SIZE_TINY,
    "backgroundColor": COLOR_BACKGROUND_PALE,
    "padding": "6px",
    "borderRadius": "3px",
    "marginBottom": "0",
    "whiteSpace": "pre-wrap",
    "wordBreak": "break-all"
}

PROPERTY_SIMPLE_VALUE_STYLE = {
    "color": COLOR_TEXT_DARK,
    "fontSize": FONT_SIZE_SMALL
}

PROPERTY_LABEL_STYLE = {
    "color": COLOR_TEXT_MUTED,
    "fontSize": FONT_SIZE_XSMALL
}

# Performance Metrics Styles
PERFORMANCE_CONTAINER_STYLE = {
    "backgroundColor": COLOR_BACKGROUND_PALE,
    "borderRadius": "4px",
    "padding": "8px 12px",
    "marginBottom": "8px",
    "border": f"1px solid {COLOR_CODE_BACKGROUND}"
}

PERFORMANCE_METRIC_ICON_STYLE = {
    "color": COLOR_TEXT_MUTED,
    "fontSize": FONT_SIZE_XTINY
}

PERFORMANCE_METRIC_LABEL_STYLE = {
    "color": COLOR_TEXT_MUTED,
    "fontSize": FONT_SIZE_TINY,
    "fontWeight": FONT_WEIGHT_MEDIUM
}

PERFORMANCE_METRIC_VALUE_STYLE = {
    "color": COLOR_TEXT_DARK,
    "fontSize": FONT_SIZE_TINY,
    "fontWeight": FONT_WEIGHT_SEMIBOLD
}

PERFORMANCE_TIP_STYLE = {
    "fontSize": FONT_SIZE_XTINY,
    "display": "block",
    "marginTop": "4px"
}

PERFORMANCE_TIP_ICON_STYLE = {
    "fontSize": FONT_SIZE_XXSMALL
}

# Alert Component Styles  
ALERT_HEADING_ICON_STYLE = {
    "fontSize": FONT_SIZE_MEDIUM
}

ALERT_TEXT_STYLE = {
    "fontSize": FONT_SIZE_MEDIUM
}

ALERT_HINT_STYLE = {
    "fontSize": FONT_SIZE_XSMALL
}

ALERT_LINK_STYLE = {
    "fontSize": FONT_SIZE_XSMALL,
    "color": "inherit",
    "textDecoration": "underline"
}

ALERT_SEPARATOR_STYLE = {
    "margin": "8px 0"
}

ALERT_DOC_LINK_ICON_STYLE = {
    "fontSize": FONT_SIZE_XTINY
}

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
