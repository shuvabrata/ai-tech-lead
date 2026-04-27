"""Display Callbacks

Callbacks for graph display, layout management, and property details.
"""

import dash_bootstrap_components as dbc
from dash import html, Input, Output, State, callback, callback_context, clientside_callback

from app.dash_app.styles import (
    DETAILS_HEADING_STYLE,
    DETAILS_LABEL_STYLE,
    DETAILS_VALUE_STYLE,
    DETAILS_CODE_STYLE,
    DETAILS_MUTED_TEXT_STYLE,
    DETAILS_SEPARATOR_STYLE,
    DETAILS_SUBHEADING_STYLE,
    FONT_SIZE_XSMALL,
    COLOR_NAVY,
    COLOR_TEXT_MUTED,
    FONT_SIZE_XTINY
)
from ..styles import build_cytoscape_stylesheet
from ..utils import toggle_details_panel, build_property_items, create_node_legend, is_node_element


@callback(
    [
        Output("graph-fullwidth-state", "data"),
        Output("graph-viz-col", "width"),
        Output("graph-details-col", "style")
    ],
    Input("graph-fullwidth-btn", "n_clicks"),
    State("graph-fullwidth-state", "data"),
    prevent_initial_call=True
)
def toggle_fullwidth(_n_clicks, is_fullwidth):
    """Toggle between full-width graph and normal view with details panel"""
    new_state = not is_fullwidth
    viz_width, panel_style = toggle_details_panel(new_state)
    return new_state, viz_width, panel_style


@callback(
    Output("graph-details-panel", "children"),
    [Input("graph-cytoscape", "selectedNodeData"),
     Input("graph-cytoscape", "selectedEdgeData"),
    Input("graph-cytoscape", "elements"),
    Input("theme-store", "data")]
)
def display_properties(selected_nodes, selected_edges, elements, theme_name):
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
        node_data = selected_nodes[0]  # Get first selected node
        # Build property table excluding internal Cytoscape fields
        exclude_keys = {'id', 'label', 'displayLabel', 'nodeType'}
        properties = {k: v for k, v in node_data.items() if k not in exclude_keys and v is not None}
        
        # Header
        header = html.Div([
            html.H6([
                html.I(className="fas fa-circle me-2", style={"color": COLOR_NAVY, "fontSize": FONT_SIZE_XTINY}),
                "Node Details"
            ], className="mb-3", style=DETAILS_HEADING_STYLE),
        ])
        
        # Basic info
        basic_info = [
            html.Div([
                html.Strong("Type: ", style=DETAILS_LABEL_STYLE),
                html.Span(node_data.get('nodeType', 'Unknown'), 
                         style=DETAILS_VALUE_STYLE)
            ], className="mb-2"),
            html.Div([
                html.Strong("Label: ", style=DETAILS_LABEL_STYLE),
                html.Span(node_data.get('label', 'N/A'), 
                         style=DETAILS_VALUE_STYLE)
            ], className="mb-2"),
            html.Div([
                html.Strong("ID: ", style=DETAILS_LABEL_STYLE),
                html.Code(str(node_data.get('id', 'N/A')), 
                         style=DETAILS_CODE_STYLE)
            ], className="mb-3"),
            html.Hr(style=DETAILS_SEPARATOR_STYLE)
        ]
        
        # Properties section
        if properties:
            properties_section = [
                html.H6("Properties", style=DETAILS_SUBHEADING_STYLE),
                html.Div(build_property_items(properties))
            ]
        else:
            properties_section = [
                html.P("No additional properties", className="text-muted", style=DETAILS_MUTED_TEXT_STYLE)
            ]
        
        # Phase 1.1b: Add Expand Node button
        expand_button = html.Div([
            html.Hr(style={"margin": "16px 0"}),
            dbc.Button(
                [html.I(className="fas fa-project-diagram me-2"), "Expand Node"],
                id="expand-node-btn",
                color="primary",
                size="sm",
                outline=True,
                className="w-100",
                style={"fontSize": FONT_SIZE_XSMALL}
            ),
            html.Small(
                "Load connected neighbors",
                className="text-muted d-block text-center mt-1",
                style={"fontSize": FONT_SIZE_XTINY}
            )
        ], className="mt-3")
        
        return html.Div([header] + basic_info + properties_section + [expand_button])
    
    # Edge was selected (selectedEdgeData returns a list)
    elif selected_edges and len(selected_edges) > 0:
        edge_data = selected_edges[0]  # Get first selected edge
        # Build property table excluding internal Cytoscape fields
        exclude_keys = {'id', 'source', 'target', 'label', 'relType'}
        properties = {k: v for k, v in edge_data.items() if k not in exclude_keys and v is not None}
        
        # Header
        header = html.Div([
            html.H6([
                html.I(className="fas fa-arrow-right me-2", style={"color": COLOR_TEXT_MUTED, "fontSize": FONT_SIZE_XSMALL}),
                "Relationship Details"
            ], className="mb-3", style=DETAILS_HEADING_STYLE),
        ])
        
        # Basic info
        basic_info = [
            html.Div([
                html.Strong("Type: ", style=DETAILS_LABEL_STYLE),
                html.Span(edge_data.get('relType', edge_data.get('label', 'Unknown')), 
                         style=DETAILS_VALUE_STYLE)
            ], className="mb-2"),
            html.Div([
                html.Strong("From: ", style=DETAILS_LABEL_STYLE),
                html.Code(str(edge_data.get('source', 'N/A')), 
                         style=DETAILS_CODE_STYLE)
            ], className="mb-2"),
            html.Div([
                html.Strong("To: ", style=DETAILS_LABEL_STYLE),
                html.Code(str(edge_data.get('target', 'N/A')), 
                         style=DETAILS_CODE_STYLE)
            ], className="mb-2"),
            html.Div([
                html.Strong("ID: ", style=DETAILS_LABEL_STYLE),
                html.Code(str(edge_data.get('id', 'N/A')), 
                         style=DETAILS_CODE_STYLE)
            ], className="mb-3"),
            html.Hr(style=DETAILS_SEPARATOR_STYLE)
        ]
        
        # Properties section
        if properties:
            properties_section = [
                html.H6("Properties", style=DETAILS_SUBHEADING_STYLE),
                html.Div(build_property_items(properties))
            ]
        else:
            properties_section = [
                html.P("No additional properties", className="text-muted", style=DETAILS_MUTED_TEXT_STYLE)
            ]
        
        return html.Div([header] + basic_info + properties_section)
    
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


# Phase 1.2.3: Edge Hover Highlighting
# Clientside callback to attach edge hover listeners with highlighting behavior
clientside_callback(
    """
    function(elements) {
        // Get the Cytoscape instance
        const elem = document.getElementById('graph-cytoscape');
        if (!elem || !elem._cyreg || !elem._cyreg.cy) {
            return window.dash_clientside.no_update;
        }
        
        const cy = elem._cyreg.cy;
        
        // Check if we've already attached the listeners (avoid duplicates)
        if (!cy._edgeHoverListenerAttached) {
            let hoverTimeout = null;
            let isHovering = false;
            
            // Mouseover handler with 50ms debounce
            cy.on('mouseover', 'edge', function(evt) {
                const edge = evt.target;
                
                // Clear any pending timeout
                if (hoverTimeout) {
                    clearTimeout(hoverTimeout);
                }
                
                // Debounce: wait 50ms before applying highlight
                hoverTimeout = setTimeout(function() {
                    isHovering = true;
                    
                    // Get source and target nodes
                    const sourceNode = edge.source();
                    const targetNode = edge.target();
                    
                    // Highlight the edge and connected nodes
                    edge.addClass('highlighted');
                    sourceNode.addClass('highlighted');
                    targetNode.addClass('highlighted');
                    
                    // Dim all other elements
                    cy.elements().not(edge).not(sourceNode).not(targetNode).addClass('dimmed');
                }, 50);
            });
            
            // Mouseout handler
            cy.on('mouseout', 'edge', function(evt) {
                // Clear any pending timeout
                if (hoverTimeout) {
                    clearTimeout(hoverTimeout);
                    hoverTimeout = null;
                }
                
                // Only remove classes if we actually applied them
                if (isHovering) {
                    // Remove all highlight and dim classes
                    cy.elements().removeClass('highlighted dimmed');
                    isHovering = false;
                }
            });
            
            // Mark that we've attached the listeners
            cy._edgeHoverListenerAttached = true;
            console.log('[Phase 1.2.3] Edge hover listeners attached with 50ms debounce');
        }
        
        return window.dash_clientside.no_update;
    }
    """,
    Output("graph-cytoscape", "className"),  # Dummy output
    Input("graph-cytoscape", "elements"),
    prevent_initial_call=False
)
