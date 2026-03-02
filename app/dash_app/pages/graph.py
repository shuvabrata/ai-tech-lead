"""Graph Visualization Page

This page allows users to:
- Enter and execute Cypher queries
- View graph results (nodes and relationships)
- Display tabular results for non-graph queries
"""

import os
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, clientside_callback
import dash_cytoscape as cyto
import requests

from app.settings import settings

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT

# Cytoscape stylesheet for graph visualization
CYTOSCAPE_STYLESHEET = [
    # Default node style
    {
        'selector': 'node',
        'style': {
            'label': 'data(label)',
            'background-color': '#6c757d',
            'color': '#fff',
            'text-valign': 'center',
            'text-halign': 'center',
            'font-size': '11px',
            'font-weight': '500',
            'width': '60px',
            'height': '60px',
            'border-width': '2px',
            'border-color': '#495057',
            'text-wrap': 'wrap',
            'text-max-width': '80px'
        }
    },
    # Project nodes - Blue
    {
        'selector': 'node[nodeType = "Project"]',
        'style': {
            'background-color': '#0d6efd',
            'border-color': '#0a58ca',
            'width': '70px',
            'height': '70px'
        }
    },
    # Person nodes - Purple
    {
        'selector': 'node[nodeType = "Person"]',
        'style': {
            'background-color': '#6f42c1',
            'border-color': '#59359a',
            'width': '65px',
            'height': '65px'
        }
    },
    # Branch nodes - Teal
    {
        'selector': 'node[nodeType = "Branch"]',
        'style': {
            'background-color': '#20c997',
            'border-color': '#198754',
            'width': '55px',
            'height': '55px'
        }
    },
    # Epic nodes - Orange
    {
        'selector': 'node[nodeType = "Epic"]',
        'style': {
            'background-color': '#fd7e14',
            'border-color': '#dc6502',
            'width': '65px',
            'height': '65px'
        }
    },
    # Issue nodes - Yellow
    {
        'selector': 'node[nodeType = "Issue"]',
        'style': {
            'background-color': '#ffc107',
            'border-color': '#cc9a06',
            'color': '#000',
            'width': '55px',
            'height': '55px'
        }
    },
    # Repository nodes - Cyan
    {
        'selector': 'node[nodeType = "Repository"]',
        'style': {
            'background-color': '#0dcaf0',
            'border-color': '#0aa2c0',
            'width': '65px',
            'height': '65px'
        }
    },
    # Edge styles
    {
        'selector': 'edge',
        'style': {
            'width': 2,
            'line-color': '#adb5bd',
            'target-arrow-color': '#adb5bd',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'label': 'data(label)',
            'font-size': '9px',
            'text-rotation': 'autorotate',
            'text-margin-y': -10,
            'text-background-color': '#fff',
            'text-background-opacity': 0.8,
            'text-background-padding': '3px'
        }
    },
    # Node selected state (click to select)
    {
        'selector': 'node:selected',
        'style': {
            'border-width': '4px',
            'border-color': '#ffc107',
            'border-style': 'solid',
            'z-index': 9999
        }
    },
    # Edge selected state (click to select)
    {
        'selector': 'edge:selected',
        'style': {
            'width': 4,
            'line-color': '#ffc107',
            'target-arrow-color': '#ffc107',
            'z-index': 9999
        }
    }
]


def get_layout():
    """Return the graph page layout"""
    return html.Div([
        # Page Header
        html.H2("Graph Visualization", className="mb-4", style={"fontWeight": "600", "color": "#1a1a1a"}),
        
        html.P(
            "Execute Cypher queries against your Neo4j database and visualize the results.", 
            className="mb-4",
            style={"color": "#666", "fontSize": "15px"}
        ),
        
        # Results Section
        html.Div([
            html.H5("Results", className="mb-3", style={"fontWeight": "500", "color": "#333"}),
            
            dcc.Loading(
                id="graph-loading",
                type="circle",
                color="#0d6efd",
                children=[
                    dbc.Row([
                        # Graph visualization area
                        dbc.Col([
                            # Graph visualization container
                            html.Div(
                                id="graph-cytoscape-container",
                                style={"display": "none"},  # Hidden by default
                                children=[
                                    # Layout controls
                                    dbc.Row([
                                        dbc.Col([
                                            html.Label("Layout Algorithm:", 
                                                      style={"fontSize": "13px", "fontWeight": "500", "color": "#495057", "marginRight": "8px"}),
                                            dbc.Select(
                                                id="graph-layout-selector",
                                                options=[
                                                    {"label": "Force-Directed (cose)", "value": "cose"},
                                                    {"label": "Circle", "value": "circle"},
                                                    {"label": "Grid", "value": "grid"},
                                                    {"label": "Hierarchical (breadthfirst)", "value": "breadthfirst"},
                                                    {"label": "Concentric", "value": "concentric"}
                                                ],
                                                value="cose",
                                                style={"width": "250px", "display": "inline-block"}
                                            )
                                        ], width="auto"),
                                        dbc.Col([
                                            dbc.ButtonGroup([
                                                dbc.Button(
                                                    [html.I(className="fas fa-expand me-1"), "Fit to Screen"],
                                                    id="graph-fit-btn",
                                                    color="light",
                                                    size="sm",
                                                    style={"fontSize": "12px"}
                                                ),
                                                dbc.Button(
                                                    [html.I(className="fas fa-redo me-1"), "Reset View"],
                                                    id="graph-reset-btn",
                                                    color="light",
                                                    size="sm",
                                                    style={"fontSize": "12px"}
                                                )
                                            ], size="sm")
                                        ], width="auto", className="ms-auto")
                                    ], className="mb-3", align="center"),
                                    
                                    cyto.Cytoscape(
                                        id="graph-cytoscape",
                                        elements=[],
                                        layout={'name': 'cose', 'animate': True},
                                        style={
                                            'width': '100%',
                                            'height': '600px',
                                            'backgroundColor': '#fafafa',
                                            'borderRadius': '8px'
                                        },
                                        stylesheet=CYTOSCAPE_STYLESHEET,
                                        userZoomingEnabled=True,
                                        userPanningEnabled=True,
                                        wheelSensitivity=0.2,
                                        minZoom=0.5,
                                        maxZoom=3
                            )
                        ]
                    ),
                    
                    # Table container for tabular results
                    html.Div(
                        id="graph-table-container",
                        style={"display": "none"}  # Hidden by default
                    ),
                    
                    # Default empty state
                    html.Div(
                        id="graph-results-container",
                        style={
                            "minHeight": "400px",
                            "padding": "20px"
                        },
                        children=[
                            html.Div(
                                [
                                    html.I(className="fas fa-project-diagram fa-3x mb-3", style={"color": "#ccc"}),
                                    html.P(
                                        "No results yet. Enter a Cypher query above and click 'Execute Query' to visualize data.",
                                        style={"color": "#999", "fontSize": "15px"}
                                    )
                                ],
                                className="text-center",
                                style={"marginTop": "80px"}
                            )
                        ]
                    )
                        ], width=8),
                        
                        # Property details panel
                        dbc.Col([
                            html.Div(
                                id="graph-details-panel",
                                style={
                                    "backgroundColor": "#f8f9fa",
                                    "borderRadius": "8px",
                                    "border": "1px solid #dee2e6",
                                    "padding": "16px",
                                    "minHeight": "600px",
                                    "maxHeight": "600px",
                                    "overflowY": "auto"
                                },
                                children=[
                                    html.Div([
                                        html.I(className="fas fa-info-circle fa-2x mb-2", style={"color": "#adb5bd"}),
                                        html.P(
                                            "Click a node or edge to view details",
                                            className="text-muted mb-0",
                                            style={"fontSize": "14px"}
                                        )
                                    ], className="text-center", style={"marginTop": "200px"})
                                ]
                            )
                        ], width=4)
                    ])
                ]
            )
        ], style={
            "backgroundColor": "#ffffff",
            "borderRadius": "12px",
            "border": "1px solid #e0e0e0",
            "padding": "24px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"
        }),
        
        # Query Input Section
        html.Div([
            html.H5("Cypher Query", className="mb-3", style={"fontWeight": "500", "color": "#333"}),
            
            dbc.Textarea(
                id="graph-query-input",
                placeholder="MATCH (n:Project)-[r]->(m)\nRETURN n, r, m\nLIMIT 10",
                style={
                    "height": "150px",
                    "borderRadius": "12px",
                    "border": "2px solid #e0e0e0",
                    "padding": "12px 16px",
                    "fontSize": "14px",
                    "fontFamily": "Consolas, Monaco, 'Courier New', monospace",
                    "resize": "vertical",
                    "transition": "border-color 0.2s"
                },
                className="mb-2"
            ),
            
            # Validation message container
            html.Div(id="query-validation-message", className="mb-3"),
            
            html.Div([
                dbc.Button(
                    [html.I(className="fas fa-play me-2"), "Execute Query"],
                    id="graph-execute-btn",
                    color="primary",
                    style={
                        "borderRadius": "8px",
                        "fontWeight": "500",
                        "fontSize": "15px",
                        "padding": "10px 24px",
                        "boxShadow": "0 2px 6px rgba(13, 110, 253, 0.25)"
                    }
                ),
                html.Small(
                    "Note: Only read-only queries (MATCH, RETURN) are allowed for security.",
                    className="ms-3 text-muted",
                    style={"fontSize": "13px"}
                )
            ], className="d-flex align-items-center mb-4")
        ], style={
            "backgroundColor": "#ffffff",
            "borderRadius": "12px",
            "border": "1px solid #e0e0e0",
            "padding": "24px",
            "marginBottom": "24px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"
        }),
        
        # Hidden data store for graph data
        dcc.Store(id="graph-data-store", data=None),
        
        # Session store for query history (optional, for future use)
        dcc.Store(id="graph-query-history", data=[]),
        
        # Hidden div for triggering fit-to-screen via clientside callback
        html.Div(id="graph-fit-trigger", style={"display": "none"}),
        
    ], className="mt-4")


def neo4j_to_cytoscape(graph_response):
    """Transform Neo4j graph response to Cytoscape elements format
    
    Args:
        graph_response (dict): Graph response from backend API containing:
            - nodes: List of node objects with id, labels, properties
            - relationships: List of relationship objects with id, type, startNode, endNode, properties
    
    Returns:
        list: List of Cytoscape elements (nodes and edges)
    """
    elements = []
    
    # Transform nodes
    for node in graph_response.get("nodes", []):
        # Use the first label as the main label, or 'Node' if no labels
        node_label = node.get("labels", ["Node"])[0] if node.get("labels") else "Node"
        
        # Try to get a display name from common properties
        display_name = (
            node.get("properties", {}).get("name") or 
            node.get("properties", {}).get("title") or 
            node.get("properties", {}).get("label") or 
            node_label
        )
        
        # Create Cytoscape node element
        cyto_node = {
            'data': {
                'id': node['id'],
                'label': display_name,
                'nodeType': node_label,
                **node.get('properties', {})
            }
        }
        elements.append(cyto_node)
    
    # Transform relationships
    for rel in graph_response.get("relationships", []):
        # Create Cytoscape edge element
        cyto_edge = {
            'data': {
                'id': rel['id'],
                'source': rel['startNode'],
                'target': rel['endNode'],
                'label': rel['type'],
                'relType': rel['type'],
                **rel.get('properties', {})
            }
        }
        elements.append(cyto_edge)
    
    return elements


def _create_error_alert(message, alert_type='danger', hint=None, heading="Query Execution Failed"):
    """Create an error/warning alert component
    
    Args:
        message (str): Main error message
        alert_type (str): Bootstrap alert type ('danger', 'warning', 'info')
        hint (str, optional): Additional hint text
        heading (str, optional): Alert heading
    
    Returns:
        html.Div: Alert component
    """
    icon_map = {
        'danger': 'fa-times-circle',
        'warning': 'fa-exclamation-triangle',
        'info': 'fa-info-circle'
    }
    icon = icon_map.get(alert_type, 'fa-exclamation-triangle')
    
    if heading:
        alert_content = [
            html.H5([
                html.I(className=f"fas {icon} me-2"),
                heading
            ], className="alert-heading mb-2"),
            html.P(message, className="mb-1"),
            html.Small(hint, className="text-muted") if hint else None
        ]
    else:
        alert_content = [
            html.I(className=f"fas {icon} me-2"),
            message
        ]
    
    return html.Div([
        dbc.Alert(alert_content, color=alert_type)
    ])


def _create_table_display(raw_results, result_count):
    """Create a table display for tabular query results
    
    Args:
        raw_results (list): List of result dictionaries
        result_count (int): Total number of results
    
    Returns:
        html.Div: Table display component with success alert
    """
    if raw_results and len(raw_results) > 0:
        # Get column names from first result
        columns = list(raw_results[0].keys()) if raw_results else []
        
        # Create table
        table = dbc.Table([
            html.Thead(
                html.Tr([html.Th(col) for col in columns])
            ),
            html.Tbody([
                html.Tr([
                    html.Td(str(row.get(col, ""))) for col in columns
                ]) for row in raw_results
            ])
        ], bordered=True, striped=True, hover=True, responsive=True, className="mb-0")
        
        return html.Div([
            dbc.Alert([
                html.I(className="fas fa-check-circle me-2"),
                f"Query executed successfully! Retrieved {result_count} result(s)."
            ], color="success", className="mb-3"),
            table
        ])
    else:
        # Empty results
        return dbc.Alert([
            html.I(className="fas fa-info-circle me-2"),
            "Query executed successfully but returned no results."
        ], color="info")


def _create_graph_success_alert(node_count, rel_count):
    """Create a success alert for graph query results
    
    Args:
        node_count (int): Number of nodes
        rel_count (int): Number of relationships
    
    Returns:
        dbc.Alert: Success alert component
    """
    return dbc.Alert([
        html.I(className="fas fa-check-circle me-2"),
        f"Query executed successfully! Displaying {node_count} nodes and {rel_count} relationships."
    ], color="success", className="mb-0")


def _format_property_value(value):
    """Format a property value for display in the property panel
    
    Args:
        value: Property value (can be dict, list, or primitive type)
    
    Returns:
        html component: Formatted value as html.Pre for complex types or html.Span for primitives
    """
    if isinstance(value, (dict, list)):
        return html.Pre(
            str(value),
            style={
                "fontSize": "11px",
                "backgroundColor": "#f8f9fa",
                "padding": "6px",
                "borderRadius": "3px",
                "marginBottom": "0",
                "whiteSpace": "pre-wrap",
                "wordBreak": "break-all"
            }
        )
    else:
        return html.Span(
            str(value),
            style={"color": "#212529", "fontSize": "13px"}
        )


def _build_property_items(properties):
    """Build property display items from a properties dictionary
    
    Args:
        properties (dict): Dictionary of property key-value pairs
    
    Returns:
        list: List of html.Div components displaying properties
    """
    prop_items = []
    for key, value in sorted(properties.items()):
        prop_items.append(
            html.Div([
                html.Strong(f"{key}: ", style={"color": "#6c757d", "fontSize": "12px"}),
                _format_property_value(value)
            ], className="mb-2")
        )
    return prop_items


# Clientside callback to fit graph to screen without re-running layout
clientside_callback(
    """
    function(n_clicks) {
        if (n_clicks) {
            // Get the Cytoscape instance
            const elem = document.getElementById('graph-cytoscape');
            if (elem && elem._cyreg && elem._cyreg.cy) {
                // Call fit() to zoom/pan to show all elements
                elem._cyreg.cy.fit(null, 30);  // 30px padding
            }
        }
        return n_clicks || 0;
    }
    """,
    Output("graph-fit-trigger", "children"),
    Input("graph-fit-btn", "n_clicks"),
    prevent_initial_call=True
)


# Callback for real-time query validation
@callback(
    Output("query-validation-message", "children"),
    Input("graph-query-input", "value")
)
def validate_query(query_text):
    """Validate Cypher query and provide real-time feedback"""
    # Empty query - no message
    if not query_text or not query_text.strip():
        return None
    
    query_upper = query_text.strip().upper()
    
    # Check for write operations (not allowed)
    write_keywords = ['CREATE', 'MERGE', 'SET', 'DELETE', 'REMOVE', 'DROP']
    for keyword in write_keywords:
        if f' {keyword} ' in f' {query_upper} ' or query_upper.startswith(f'{keyword} '):
            return dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                f"Write operations ({keyword}) are not allowed for security reasons. Only read-only queries (MATCH, RETURN) are permitted."
            ], color="danger", className="mb-0", style={"fontSize": "13px"})
    
    # Check if query starts with valid read keywords
    valid_starts = ['MATCH', 'RETURN', 'WITH', 'UNWIND', 'CALL', 'OPTIONAL']
    starts_valid = any(query_upper.startswith(keyword) for keyword in valid_starts)
    
    if not starts_valid:
        return dbc.Alert([
            html.I(className="fas fa-info-circle me-2"),
            "Query should typically start with MATCH, RETURN, or other read-only keywords."
        ], color="warning", className="mb-0", style={"fontSize": "13px"})
    
    # Check for missing LIMIT (performance warning)
    if 'LIMIT' not in query_upper and 'MATCH' in query_upper:
        return dbc.Alert([
            html.I(className="fas fa-lightbulb me-2"),
            "Consider adding a LIMIT clause to improve query performance."
        ], color="info", className="mb-0", style={"fontSize": "13px"})
    
    # Query looks good
    return None


# Callback to execute Cypher query and display results
@callback(
    [Output("graph-data-store", "data"),
     Output("graph-cytoscape", "elements"),
     Output("graph-cytoscape-container", "style"),
     Output("graph-table-container", "children"),
     Output("graph-table-container", "style"),
     Output("graph-results-container", "children"),
     Output("graph-results-container", "style"),
     Output("graph-details-panel", "style")],
    [Input("graph-execute-btn", "n_clicks")],
    [State("graph-query-input", "value")],
    prevent_initial_call=True
)
def execute_query(n_clicks, query_text):
    """Execute Cypher query and display results"""
    # Default empty states
    empty_elements = []
    hide_style = {"display": "none"}
    show_style = {"display": "block"}
    default_container_style = {"minHeight": "400px", "padding": "20px"}
    panel_visible_style = {
        "display": "block",
        "backgroundColor": "#f8f9fa",
        "borderRadius": "8px",
        "border": "1px solid #dee2e6",
        "padding": "16px",
        "minHeight": "600px",
        "maxHeight": "600px",
        "overflowY": "auto"
    }
    
    # Validate query not empty
    if not query_text or not query_text.strip():
        error_display = _create_error_alert(
            "Please enter a Cypher query before executing.",
            alert_type='warning',
            heading=None
        )
        return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style
    
    # Get API base URL
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    try:
        # Send query to API
        response = requests.post(
            f"{api_base}/api/v1/graph/query",
            json={"query": query_text},
            timeout=TIMEOUT_SECONDS
        )
        
        # Handle error responses
        if response.status_code != 200:
            error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
            error_message = error_data.get("detail", {}).get("error", str(response.text))
            error_hint = error_data.get("detail", {}).get("hint", "")
            
            error_display = _create_error_alert(error_message, hint=error_hint)
            return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style
        
        response.raise_for_status()
        data = response.json()
        
        # Check if result is a graph or tabular data
        is_graph = data.get("isGraph", False)
        node_count = len(data.get("nodes", []))
        rel_count = len(data.get("relationships", []))
        result_count = data.get("resultCount", 0)
        
        if is_graph:
            # Transform data to Cytoscape format
            cyto_elements = neo4j_to_cytoscape(data)
            success_alert = _create_graph_success_alert(node_count, rel_count)
            
            # Show graph, hide table and default, show details panel
            return (
                data,
                cyto_elements,
                show_style,
                success_alert,
                show_style,
                None,
                hide_style,
                panel_visible_style  # Show details panel for graph results
            )
        else:
            # Tabular results - create table
            raw_results = data.get("rawResults", [])
            table_display = _create_table_display(raw_results, result_count)
            
            # Show table, hide graph and default, hide details panel
            return (
                data,
                empty_elements,
                hide_style,
                table_display,
                show_style,
                None,
                hide_style,
                hide_style  # Hide details panel for tabular results
            )
        
    except requests.exceptions.Timeout:
        error_display = _create_error_alert(
            f"Query timeout: The query took longer than {TIMEOUT_SECONDS} seconds to execute.",
            alert_type='warning',
            heading=None
        )
        return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style
    
    except requests.exceptions.ConnectionError:
        error_display = _create_error_alert(
            "Connection error: Unable to connect to the backend API. Please ensure the server is running.",
            heading=None
        )
        return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style
    
    except requests.exceptions.HTTPError as e:
        error_display = _create_error_alert(f"HTTP Error: {str(e)}", heading=None)
        return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style
    
    except Exception as e:
        error_display = _create_error_alert(f"Unexpected error: {str(e)}", heading=None)
        return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style


# Callback to display property details when node or edge is selected
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
                html.Div(_build_property_items(properties))
            ]
        else:
            properties_section = [
                html.P("No additional properties", className="text-muted", style={"fontSize": "13px", "fontStyle": "italic"})
            ]
        
        return html.Div([header] + basic_info + properties_section)
    
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
                html.Div(_build_property_items(properties))
            ]
        else:
            properties_section = [
                html.P("No additional properties", className="text-muted", style={"fontSize": "13px", "fontStyle": "italic"})
            ]
        
        return html.Div([header] + basic_info + properties_section)
    
    # Nothing selected
    return empty_state


# Callback to update graph layout when selector changes or reset is clicked
@callback(
    Output("graph-cytoscape", "layout"),
    [Input("graph-layout-selector", "value"),
     Input("graph-reset-btn", "n_clicks")],
    [State("graph-cytoscape", "layout")],
    prevent_initial_call=True
)
def update_layout(layout_name, reset_clicks, current_layout):
    """Update the Cytoscape graph layout algorithm or trigger layout reset"""
    from dash import callback_context
    
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

