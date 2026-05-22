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
from ..styles import build_cytoscape_stylesheet
from ..utils import toggle_details_panel, build_property_items, create_node_legend, is_node_element


_INTERNAL_NEO4J_KEYS = {"ID", "elementID", "elementId"}


def _is_visible_property_key(key):
    """Return True when a property key is safe to expose in the UI."""
    if key in _INTERNAL_NEO4J_KEYS:
        return False
    return not str(key).startswith("_")


def _build_visible_properties(data, exclude_keys):
    """Build a filtered property dictionary for the details panel."""
    return {
        key: value
        for key, value in data.items()
        if key not in exclude_keys and value is not None and _is_visible_property_key(key)
    }


def _resolve_edge_endpoint_id(edge_data, endpoint):
    """Resolve an edge endpoint using explicit *_id fields before Cytoscape ids."""
    for key in (f"{endpoint}_id", f"{endpoint}Id", endpoint):
        value = edge_data.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, dict):
            nested_id = value.get("id")
            if nested_id not in (None, ""):
                return nested_id
            continue
        return value
    return "N/A"


def _build_properties_table(items):
    """Render a list of (key, value) pairs as an Executive Dashboard tabular layout."""
    rows = []
    for key, value in items:
        str_value = str(value)
        # Use monospace style for IDs and technical-looking values
        is_mono = key in ("id",) or (len(str_value) > 16 and " " not in str_value)
        value_cell = (
            html.Code(str_value, style=DETAILS_TABLE_VALUE_MONO_STYLE)
            if is_mono
            else html.Span(str_value, style=DETAILS_TABLE_VALUE_STYLE)
        )
        rows.append(
            html.Tr([
                html.Td(key, style=DETAILS_TABLE_KEY_STYLE),
                html.Td(value_cell, style={"padding": "6px 0 6px 8px", "borderBottom": "1px solid var(--color-border-light)", "verticalAlign": "top", "wordBreak": "break-word"}),
            ])
        )
    return html.Table(html.Tbody(rows), style=DETAILS_TABLE_STYLE)


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
        # Build property table with all visible keys, including id, label, nodeType, sorted alphabetically

        # Exclude internal/display-only fields from the properties table
        # 'id' is the Neo4j element_id used by Cytoscape internals — not shown
        # 'wba_id' is the canonical node identifier (e.g. 'github::Person::alice') — shown as 'id' at top
        exclude_keys = {'displayLabel', 'id', 'wba_id', 'label', 'nodeType', 'elementType'}
        properties = _build_visible_properties(node_data, exclude_keys)
        # Show the wba_id as 'id' at the top of the sorted list
        wba_id = node_data.get('wba_id') or node_data.get('id')
        sorted_items = sorted(properties.items())
        if wba_id is not None:
            sorted_items = [('id', wba_id)] + sorted_items

        # Header: node type label with navy left-accent
        header = html.Div([
            html.Div(
                node_data.get('label', 'N/A'),
                style=DETAILS_PANEL_HEADER_STYLE
            ),
            html.Div(
                node_data.get('nodeType', 'Unknown'),
                style=DETAILS_PANEL_SUBTYPE_STYLE
            ),
        ], className="mb-3")

        # Properties table (all keys sorted alphabetically, id pinned to top)
        if sorted_items:
            properties_section = [_build_properties_table(sorted_items)]
        else:
            properties_section = [
                html.P("No properties", className="text-muted", style=DETAILS_MUTED_TEXT_STYLE)
            ]

        # Expand Node button
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

        return html.Div([header] + properties_section + [expand_button])
    
    # Edge was selected (selectedEdgeData returns a list)
    elif selected_edges and len(selected_edges) > 0:
        edge_data = selected_edges[0]  # Get first selected edge
        # Build property table excluding internal Cytoscape fields
        exclude_keys = {'id', 'source', 'target', 'label', 'relType'}
        properties = _build_visible_properties(edge_data, exclude_keys)

        source_id = _resolve_edge_endpoint_id(edge_data, "source")
        target_id = _resolve_edge_endpoint_id(edge_data, "target")
        
        # Header
        header = html.Div([
            html.Div(
                edge_data.get('relType', edge_data.get('label', 'Unknown')),
                style=DETAILS_PANEL_HEADER_STYLE
            ),
            html.Div("Relationship", style=DETAILS_PANEL_SUBTYPE_STYLE),
        ], className="mb-3")

        # Fixed relationship metadata as a table
        meta_items = [
            ("from", source_id),
            ("to", target_id),
        ]
        if properties:
            meta_items += sorted(properties.items())

        return html.Div([header, _build_properties_table(meta_items)])
    
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
