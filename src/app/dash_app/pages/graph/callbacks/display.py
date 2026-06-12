"""Display Callbacks

Callbacks for graph display, layout management, and property details.
"""

import dash_bootstrap_components as dbc
from dash import html, Input, Output, State, callback, callback_context

from app.dash_app.styles import (
    DETAILS_HEADING_STYLE,
    DETAILS_LABEL_STYLE,
    DETAILS_VALUE_STYLE,
    DETAILS_CODE_STYLE,
    DETAILS_MUTED_TEXT_STYLE,
    DETAILS_SEPARATOR_STYLE,
    DETAILS_SUBHEADING_STYLE,
    DETAILS_PANEL_HEADER_STYLE,
    DETAILS_PANEL_SUBTYPE_STYLE,
    DETAILS_TABLE_STYLE,
    DETAILS_TABLE_KEY_STYLE,
    DETAILS_TABLE_VALUE_STYLE,
    DETAILS_TABLE_VALUE_MONO_STYLE,
    FONT_SIZE_XSMALL,
    COLOR_NAVY,
    COLOR_TEXT_MUTED,
    FONT_SIZE_XTINY
)
from app.dash_app.components.common import build_element_properties_content, register_edge_hover_dimming_callback, register_fullwidth_callback
from ..styles import build_cytoscape_stylesheet
from ..utils import create_node_legend, is_node_element

register_fullwidth_callback("graph")
register_edge_hover_dimming_callback("graph-cytoscape")


@callback(
    Output("graph-details-panel", "children"),
    [Input("graph-cytoscape", "selectedNodeData"),
     Input("graph-cytoscape", "selectedEdgeData"),
     Input("theme-store", "data")],
    State("graph-cytoscape", "elements"),
)
def display_properties(selected_nodes, selected_edges, theme_name, elements):
    """Display detailed properties of selected node or edge"""
    # Extract unique node types from current graph elements
    node_types = set()
    if elements:
        for element in elements:
            if is_node_element(element):
                node_type = element.get('data', {}).get('nodeType')
                if node_type:
                    node_types.add(node_type)
    
    # Default state: show legend with current node types (or empty state if no graph)
    active_theme = theme_name or "executive-light"
    legend_state = create_node_legend(list(node_types) if node_types else None, theme_name=active_theme)
    
    # Node was selected (selectedNodeData returns a list)
    if selected_nodes and len(selected_nodes) > 0:
        return build_element_properties_content(selected_nodes[0], expand_node_enabled=True)

    # Edge was selected (selectedEdgeData returns a list)
    if selected_edges and len(selected_edges) > 0:
        return build_element_properties_content(selected_edges[0], expand_node_enabled=True)

    # Nothing selected - show legend
    return legend_state


@callback(
    Output("graph-cytoscape", "layout"),
    [Input("graph-layout-selector", "value"),
     Input("graph-reset-btn", "n_clicks")],
    [State("graph-cytoscape", "layout")],
    prevent_initial_call=True
)
def update_layout(layout_name, reset_clicks, current_layout):
    """Update the Cytoscape graph layout algorithm or trigger layout reset"""
    # Determine which input triggered the callback
    if not callback_context.triggered:
        return current_layout
    
    trigger_id = callback_context.triggered[0]['prop_id'].split('.')[0]

    # Layout selector changed
    if trigger_id == 'graph-layout-selector':
        if layout_name == 'preset':
            return {'name': 'preset', 'fit': False, 'animate': False, 'padding': 30}
        return {'name': layout_name, 'animate': True}
    
    # Reset button clicked - re-run current layout algorithm to reset node positions
    elif trigger_id == 'graph-reset-btn':
        # Use current layout name, or default to cose
        current_name = current_layout.get('name', 'cose') if current_layout else 'cose'
        
        # Toggle a property to force Cytoscape to re-run layout on each click
        # Use click count to alternate stop value (doesn't affect visual, just forces re-render)
        click_count = reset_clicks or 0
        stop_value = 1000 if click_count % 2 == 0 else 1001
        
        # Return layout with fit=True to ensure graph fits in viewport
        if current_name == 'preset':
            return {
                'name': 'preset',
                'fit': False,
                'animate': False,
                'padding': 30,
                'stop': stop_value
            }

        return {
            'name': current_name, 
            'animate': True, 
            'fit': True, 
            'padding': 30,
            'stop': stop_value  # Alternates each click to force re-render
        }
    
    return current_layout


@callback(
    Output("graph-cytoscape", "stylesheet"),
    Input("theme-store", "data")
)
def update_graph_stylesheet(theme_name):
    """Update graph node/edge palette when the app theme changes."""
    active_theme = theme_name or "executive-light"
    return build_cytoscape_stylesheet(active_theme)



