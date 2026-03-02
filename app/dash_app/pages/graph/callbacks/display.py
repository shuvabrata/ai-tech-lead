"""Display Callbacks

Callbacks for graph display, layout management, and property details.
"""

import dash_bootstrap_components as dbc
from dash import html, Input, Output, State, callback, callback_context

from ..utils import toggle_details_panel, build_property_items


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
     Input("graph-cytoscape", "selectedEdgeData")]
)
def display_properties(selected_nodes, selected_edges):
    """Display detailed properties of selected node or edge"""
    # Default empty state
    empty_state = html.Div([
        html.I(className="fas fa-info-circle fa-2x mb-2", style={"color": "#adb5bd"}),
        html.P(
            "Click a node or edge to view details",
            className="text-muted mb-0",
            style={"fontSize": "14px"}
        )
    ], className="text-center", style={"marginTop": "200px"})
    
    # Node was selected (selectedNodeData returns a list)
    if selected_nodes and len(selected_nodes) > 0:
        node_data = selected_nodes[0]  # Get first selected node
        # Build property table excluding internal Cytoscape fields
        exclude_keys = {'id', 'label', 'nodeType'}
        properties = {k: v for k, v in node_data.items() if k not in exclude_keys and v is not None}
        
        # Header
        header = html.Div([
            html.H6([
                html.I(className="fas fa-circle me-2", style={"color": "#0d6efd", "fontSize": "10px"}),
                "Node Details"
            ], className="mb-3", style={"fontWeight": "600", "color": "#333"}),
        ])
        
        # Basic info
        basic_info = [
            html.Div([
                html.Strong("Type: ", style={"color": "#6c757d", "fontSize": "13px"}),
                html.Span(node_data.get('nodeType', 'Unknown'), 
                         style={"color": "#212529", "fontSize": "13px"})
            ], className="mb-2"),
            html.Div([
                html.Strong("Label: ", style={"color": "#6c757d", "fontSize": "13px"}),
                html.Span(node_data.get('label', 'N/A'), 
                         style={"color": "#212529", "fontSize": "13px"})
            ], className="mb-2"),
            html.Div([
                html.Strong("ID: ", style={"color": "#6c757d", "fontSize": "13px"}),
                html.Code(str(node_data.get('id', 'N/A')), 
                         style={"fontSize": "11px", "backgroundColor": "#e9ecef", "padding": "2px 6px", "borderRadius": "3px"})
            ], className="mb-3"),
            html.Hr(style={"margin": "12px 0"})
        ]
        
        # Properties section
        if properties:
            properties_section = [
                html.H6("Properties", style={"fontSize": "14px", "fontWeight": "600", "color": "#495057", "marginBottom": "12px"}),
                html.Div(build_property_items(properties))
            ]
        else:
            properties_section = [
                html.P("No additional properties", className="text-muted", style={"fontSize": "13px", "fontStyle": "italic"})
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
                style={"fontSize": "12px"}
            ),
            html.Small(
                "Load connected neighbors",
                className="text-muted d-block text-center mt-1",
                style={"fontSize": "10px"}
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
                html.I(className="fas fa-arrow-right me-2", style={"color": "#6c757d", "fontSize": "12px"}),
                "Relationship Details"
            ], className="mb-3", style={"fontWeight": "600", "color": "#333"}),
        ])
        
        # Basic info
        basic_info = [
            html.Div([
                html.Strong("Type: ", style={"color": "#6c757d", "fontSize": "13px"}),
                html.Span(edge_data.get('relType', edge_data.get('label', 'Unknown')), 
                         style={"color": "#212529", "fontSize": "13px"})
            ], className="mb-2"),
            html.Div([
                html.Strong("From: ", style={"color": "#6c757d", "fontSize": "13px"}),
                html.Code(str(edge_data.get('source', 'N/A')), 
                         style={"fontSize": "11px", "backgroundColor": "#e9ecef", "padding": "2px 6px", "borderRadius": "3px"})
            ], className="mb-2"),
            html.Div([
                html.Strong("To: ", style={"color": "#6c757d", "fontSize": "13px"}),
                html.Code(str(edge_data.get('target', 'N/A')), 
                         style={"fontSize": "11px", "backgroundColor": "#e9ecef", "padding": "2px 6px", "borderRadius": "3px"})
            ], className="mb-2"),
            html.Div([
                html.Strong("ID: ", style={"color": "#6c757d", "fontSize": "13px"}),
                html.Code(str(edge_data.get('id', 'N/A')), 
                         style={"fontSize": "11px", "backgroundColor": "#e9ecef", "padding": "2px 6px", "borderRadius": "3px"})
            ], className="mb-3"),
            html.Hr(style={"margin": "12px 0"})
        ]
        
        # Properties section
        if properties:
            properties_section = [
                html.H6("Properties", style={"fontSize": "14px", "fontWeight": "600", "color": "#495057", "marginBottom": "12px"}),
                html.Div(build_property_items(properties))
            ]
        else:
            properties_section = [
                html.P("No additional properties", className="text-muted", style={"fontSize": "13px", "fontStyle": "italic"})
            ]
        
        return html.Div([header] + basic_info + properties_section)
    
    # Nothing selected
    return empty_state


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
        return {
            'name': current_name, 
            'animate': True, 
            'fit': True, 
            'padding': 30,
            'stop': stop_value  # Alternates each click to force re-render
        }
    
    return current_layout
