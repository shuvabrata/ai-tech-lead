"""Context menu components

Right-click context menus for graph interactions.
"""

from dash import html
from app.dash_app.styles import (
    CONTEXT_MENU_CONTAINER_STYLE,
    CONTEXT_MENU_ITEM_STYLE,
    CONTEXT_MENU_DIVIDER_STYLE,
    CONTEXT_MENU_DESTRUCTIVE_STYLE
)


def create_context_menu():
    """Create the right-click context menu for nodes
    
    Returns:
        html.Div containing context menu structure
    """
    return html.Div([
        html.Div("Expand Node...", id="ctx-menu-expand", className="context-menu-item", 
                 style=CONTEXT_MENU_ITEM_STYLE),
        html.Hr(style=CONTEXT_MENU_DIVIDER_STYLE),
        html.Div("Expand Incoming Only", id="ctx-menu-expand-incoming", className="context-menu-item", 
                 style=CONTEXT_MENU_ITEM_STYLE),
        html.Div("Expand Outgoing Only", id="ctx-menu-expand-outgoing", className="context-menu-item", 
                 style=CONTEXT_MENU_ITEM_STYLE),
        html.Hr(style=CONTEXT_MENU_DIVIDER_STYLE),
        html.Div("Copy Node ID", id="ctx-menu-copy-id", className="context-menu-item", 
                 style=CONTEXT_MENU_ITEM_STYLE),
        html.Div("Remove from View", id="ctx-menu-remove", className="context-menu-item", 
                 style=CONTEXT_MENU_DESTRUCTIVE_STYLE),
    ], id="context-menu", style=CONTEXT_MENU_CONTAINER_STYLE)
