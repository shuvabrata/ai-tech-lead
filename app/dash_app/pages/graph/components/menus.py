"""Context menu components

Right-click context menus for graph interactions.
"""

from dash import html


def create_context_menu():
    """Create the right-click context menu for nodes
    
    Returns:
        html.Div containing context menu structure
    """
    return html.Div([
        html.Div("Expand Node...", id="ctx-menu-expand", className="context-menu-item", style={
            "padding": "8px 16px",
            "cursor": "pointer",
            "fontSize": "13px",
            "color": "#333"
        }),
        html.Hr(style={"margin": "4px 0", "borderTop": "1px solid #e0e0e0"}),
        html.Div("Expand Incoming Only", id="ctx-menu-expand-incoming", className="context-menu-item", style={
            "padding": "8px 16px",
            "cursor": "pointer",
            "fontSize": "13px",
            "color": "#333"
        }),
        html.Div("Expand Outgoing Only", id="ctx-menu-expand-outgoing", className="context-menu-item", style={
            "padding": "8px 16px",
            "cursor": "pointer",
            "fontSize": "13px",
            "color": "#333"
        }),
        html.Hr(style={"margin": "4px 0", "borderTop": "1px solid #e0e0e0"}),
        html.Div("Copy Node ID", id="ctx-menu-copy-id", className="context-menu-item", style={
            "padding": "8px 16px",
            "cursor": "pointer",
            "fontSize": "13px",
            "color": "#333"
        }),
        html.Div("Remove from View", id="ctx-menu-remove", className="context-menu-item", style={
            "padding": "8px 16px",
            "cursor": "pointer",
            "fontSize": "13px",
            "color": "#dc3545"  # Red for destructive action
        }),
    ], id="context-menu", style={
        "position": "fixed",
        "display": "none",
        "backgroundColor": "white",
        "border": "1px solid #ccc",
        "borderRadius": "4px",
        "boxShadow": "2px 2px 8px rgba(0,0,0,0.2)",
        "zIndex": "9999",
        "minWidth": "180px",
        "padding": "4px 0"
    })
