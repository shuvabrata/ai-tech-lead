"""Graph Visualization Page

This page allows users to:
- Enter and execute Cypher queries
- View graph results (nodes and relationships)
- Display tabular results for non-graph queries
"""

import os
from datetime import datetime
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, clientside_callback, callback_context
from dash.exceptions import PreventUpdate
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
            'background-color': '#B8B8B8',  # Pastel Neutral: Soft gray
            'color': '#333',
            'text-valign': 'center',
            'text-halign': 'center',
            'font-size': '11px',
            'font-weight': '500',
            'width': '60px',
            'height': '60px',
            'border-width': '2px',
            'border-color': '#9E9E9E',  # Darker soft gray
            'text-wrap': 'wrap',
            'text-max-width': '80px'
        }
    },
    # Project nodes - Soft Blue
    {
        'selector': 'node[nodeType = "Project"]',
        'style': {
            'background-color': '#AEC6CF',  # Pastel Neutral: Soft blue
            'border-color': '#8FA8B5',
            'width': '70px',
            'height': '70px'
        }
    },
    # Person nodes - Soft Lavender
    {
        'selector': 'node[nodeType = "Person"]',
        'style': {
            'background-color': '#C5B4E3',  # Pastel Neutral: Soft lavender
            'border-color': '#A798C7',
            'width': '65px',
            'height': '65px'
        }
    },
    # Branch nodes - Soft Mint
    {
        'selector': 'node[nodeType = "Branch"]',
        'style': {
            'background-color': '#B5E7E3',  # Pastel Neutral: Soft mint
            'border-color': '#96C9C5',
            'width': '55px',
            'height': '55px'
        }
    },
    # Epic nodes - Soft Peach
    {
        'selector': 'node[nodeType = "Epic"]',
        'style': {
            'background-color': '#F4C2B0',  # Pastel Neutral: Soft peach
            'border-color': '#D9A892',
            'width': '65px',
            'height': '65px'
        }
    },
    # Issue nodes - Soft Cream
    {
        'selector': 'node[nodeType = "Issue"]',
        'style': {
            'background-color': '#F5E6D3',  # Pastel Neutral: Soft cream
            'border-color': '#D9C8B5',
            'color': '#333',
            'width': '55px',
            'height': '55px'
        }
    },
    # Repository nodes - Soft Sage
    {
        'selector': 'node[nodeType = "Repository"]',
        'style': {
            'background-color': '#C8D5B9',  # Pastel Neutral: Soft sage
            'border-color': '#AAB89B',
            'width': '65px',
            'height': '65px'
        }
    },
    # Edge styles
    {
        'selector': 'edge',
        'style': {
            'width': 2,
            'line-color': '#C0C0C0',  # Pastel Neutral: Lighter neutral gray
            'target-arrow-color': '#C0C0C0',
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
            'border-color': '#E6D4A0',  # Pastel Neutral: Soft gold highlight
            'border-style': 'solid',
            'z-index': 9999
        }
    },
    # Edge selected state (click to select)
    {
        'selector': 'edge:selected',
        'style': {
            'width': 4,
            'line-color': '#E6D4A0',  # Pastel Neutral: Soft gold highlight
            'target-arrow-color': '#E6D4A0',
            'z-index': 9999
        }
    }
]


def get_layout():
    """Return the graph page layout"""
    return html.Div([
        # Results Section
        html.Div([
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
                                            html.Label("Layout:", 
                                                      style={"fontSize": "11px", "fontWeight": "500", "color": "#495057", "marginRight": "4px"}),
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
                                                style={"width": "200px", "display": "inline-block", "fontSize": "11px"},
                                                size="sm"
                                            )
                                        ], width="auto"),
                                        dbc.Col([
                                            dbc.ButtonGroup([
                                                dbc.Button(
                                                    [html.I(className="fas fa-expand me-1"), "Fit"],
                                                    id="graph-fit-btn",
                                                    color="light",
                                                    size="sm",
                                                    style={"fontSize": "10px", "padding": "2px 8px"}
                                                ),
                                                dbc.Button(
                                                    [html.I(className="fas fa-redo me-1"), "Reset"],
                                                    id="graph-reset-btn",
                                                    color="light",
                                                    size="sm",
                                                    style={"fontSize": "10px", "padding": "2px 8px"}
                                                ),
                                                dbc.Button(
                                                    [html.I(className="fas fa-expand-arrows-alt me-1"), "Full"],
                                                    id="graph-fullwidth-btn",
                                                    color="light",
                                                    size="sm",
                                                    style={"fontSize": "10px", "padding": "2px 8px"}
                                                )
                                            ], size="sm")
                                        ], width="auto", className="ms-auto")
                                    ], className="mb-1", align="center"),
                                    
                                    cyto.Cytoscape(
                                        id="graph-cytoscape",
                                        elements=[],
                                        layout={'name': 'cose', 'animate': True},
                                        style={
                                            'width': '100%',
                                            'height': '70vh',
                                            'backgroundColor': '#fafafa',
                                            'borderRadius': '4px'
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
                            "minHeight": "300px",
                            "padding": "8px"
                        },
                        children=[
                            html.Div(
                                [
                                    html.I(className="fas fa-project-diagram fa-lg mb-2", style={"color": "#ccc"}),
                                    html.P(
                                        "No results yet. Enter a query below and click Execute.",
                                        style={"color": "#999", "fontSize": "12px"}
                                    )
                                ],
                                className="text-center",
                                style={"marginTop": "40px"}
                            )
                        ]
                    )
                        ], id="graph-viz-col", width=8),
                        
                        # Property details panel (collapsible)
                        dbc.Col([
                            html.Div(
                                id="graph-details-panel",
                                style={
                                    "backgroundColor": "#f8f9fa",
                                    "borderRadius": "4px",
                                    "border": "1px solid #dee2e6",
                                    "padding": "8px",
                                    "height": "70vh",
                                    "overflowY": "auto"
                                },
                                children=[
                                    html.Div([
                                        html.I(className="fas fa-info-circle fa-lg mb-2", style={"color": "#adb5bd"}),
                                        html.P(
                                            "Click a node or edge to view details",
                                            className="text-muted mb-0",
                                            style={"fontSize": "12px"}
                                        )
                                    ], className="text-center", style={"marginTop": "100px"})
                                ]
                            )
                        ], id="graph-details-col", width=4)
                    ])
                ]
            )
        ], style={
            "backgroundColor": "#ffffff",
            "borderRadius": "4px",
            "border": "1px solid #e0e0e0",
            "padding": "8px",
            "marginBottom": "8px",
            "boxShadow": "0 1px 2px rgba(0,0,0,0.05)"
        }),
        
        # Query Input Section
        html.Div([
            html.H6("Query", className="mb-1", style={"fontWeight": "500", "color": "#495057", "fontSize": "13px"}),
            
            dbc.Textarea(
                id="graph-query-input",
                placeholder="MATCH (n:Project)-[r]->(m)\nRETURN n, r, m\nLIMIT 10",
                style={
                    "height": "90px",
                    "borderRadius": "4px",
                    "border": "1px solid #dee2e6",
                    "padding": "8px 10px",
                    "fontSize": "12px",
                    "fontFamily": "Consolas, Monaco, 'Courier New', monospace",
                    "resize": "vertical",
                    "transition": "border-color 0.2s"
                },
                className="mb-1"
            ),
            
            # Validation message container
            html.Div(id="query-validation-message", className="mb-1"),
            
            html.Div([
                dbc.Button(
                    [html.I(className="fas fa-play me-1"), "Execute"],
                    id="graph-execute-btn",
                    color="primary",
                    size="sm",
                    style={
                        "borderRadius": "6px",
                        "fontWeight": "500",
                        "fontSize": "13px"
                    }
                ),
                html.Small(
                    "Read-only queries only",
                    className="ms-2 text-muted",
                    style={"fontSize": "11px"}
                )
            ], className="d-flex align-items-center")
        ], style={
            "backgroundColor": "#ffffff",
            "borderRadius": "4px",
            "border": "1px solid #e0e0e0",
            "padding": "8px",
            "boxShadow": "0 1px 2px rgba(0,0,0,0.05)"
        }),
        
        # Performance metrics section (hidden by default, shown after query execution)
        html.Div(
            id="graph-performance-metrics",
            style={"display": "none"}
        ),
        
        # Hidden data store for graph data
        dcc.Store(id="graph-data-store", data=None),
        
        # Session store for query history (optional, for future use)
        dcc.Store(id="graph-query-history", data=[]),
        
        # Store for details panel collapsed state
        dcc.Store(id="graph-fullwidth-state", data=False),
        
        # Hidden div for triggering fit-to-screen via clientside callback
        html.Div(id="graph-fit-trigger", style={"display": "none"}),
        
        # --- Phase 1.1b: Node Expansion Stores ---
        # Store for tracking expanded nodes: {node_id: {direction: "both", count: 23, timestamp: "..."}}
        dcc.Store(id="expanded-nodes", data={}),
        
        # Store for tracking all loaded node IDs (for deduplication)
        dcc.Store(id="loaded-node-ids", data=[]),
        
        # Store for selected node ID when opening expansion modal
        dcc.Store(id="selected-node-for-expansion", data=None),
        
        # --- Phase 1.1c: Double-Click Expansion Communication Channel ---
        # Store for double-clicked node ID (bridge between JS and Python)
        dcc.Store(id="doubleclicked-node-store", data=None),
        
        # Store for debouncing: tracks last expansion time per node
        dcc.Store(id="expansion-debounce-store", data={}),
        
        # --- Phase 1.1d: Right-Click Context Menu Communication Channel ---
        # Store for right-clicked node data: {node_id, x, y, timestamp}
        dcc.Store(id="rightclicked-node-store", data=None),
        
        # --- Phase 1.1e: Keyboard Shortcuts ---
        # Store for keyboard shortcuts: {key, timestamp}
        dcc.Store(id="keyboard-shortcut-store", data=None),
        
        # --- Phase 1.1d: Context Menu Component ---
        html.Div([
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
        }),
        
        # --- Phase 1.1b: Node Expansion Modal ---
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Expand Node")),
            dbc.ModalBody([
                html.Div([
                    html.Label("Direction:", style={"fontWeight": "500", "fontSize": "13px", "marginBottom": "6px"}),
                    dbc.RadioItems(
                        id="expansion-direction-selector",
                        options=[
                            {"label": "Both (Incoming + Outgoing)", "value": "both"},
                            {"label": "Incoming Only", "value": "incoming"},
                            {"label": "Outgoing Only", "value": "outgoing"}
                        ],
                        value="both",
                        inline=False,
                        className="mb-3"
                    ),
                ]),
                html.Div([
                    html.Label("Limit:", style={"fontWeight": "500", "fontSize": "13px", "marginBottom": "6px"}),
                    dbc.Input(
                        id="expansion-limit-input",
                        type="number",
                        value=50,
                        min=1,
                        max=500,
                        step=1,
                        size="sm",
                        className="mb-2"
                    ),
                    html.Small("Will load up to this many neighbors (1-500)", className="text-muted", style={"fontSize": "11px"})
                ]),
                html.Div([
                    dbc.Checkbox(
                        id="expansion-auto-fit-checkbox",
                        label="Auto-fit graph after expansion",
                        value=True,
                        className="mt-3"
                    ),
                    html.Small("Automatically zoom to show all nodes", className="text-muted d-block", style={"fontSize": "11px", "marginLeft": "24px"})
                ]),
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancel", id="expansion-modal-cancel", color="secondary", size="sm", className="me-2"),
                dbc.Button("Expand", id="expansion-modal-expand", color="primary", size="sm")
            ])
        ], id="expansion-modal", is_open=False, size="md"),
        
    ])


def toggle_details_panel(is_fullwidth):
    """Helper function to calculate column widths based on panel state"""
    if is_fullwidth:
        return 12, {"display": "none"}  # Full width graph, hide panel
    else:
        return 8, {}  # Normal width, show panel


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
        # IMPORTANT: Set id AFTER spreading properties to prevent property 'id' from overwriting it
        cyto_node = {
            'data': {
                **node.get('properties', {}),  # Spread properties first
                'id': node['id'],               # Then set critical fields (can't be overwritten)
                'label': display_name,
                'nodeType': node_label
            }
        }
        elements.append(cyto_node)
    
    # Transform relationships
    for rel in graph_response.get("relationships", []):
        # Create Cytoscape edge element
        # IMPORTANT: Set id/source/target AFTER spreading properties to prevent overwriting
        cyto_edge = {
            'data': {
                **rel.get('properties', {}),  # Spread properties first
                'id': rel['id'],               # Then set critical fields (can't be overwritten)
                'source': rel['startNode'],
                'target': rel['endNode'],
                'label': rel['type'],
                'relType': rel['type']
            }
        }
        elements.append(cyto_edge)
    
    return elements


def _parse_error_response(error_data, status_code):
    """Parse backend error response and provide user-friendly messages with helpful links
    
    Args:
        error_data (dict): Error response from backend API
        status_code (int): HTTP status code
    
    Returns:
        tuple: (message, hint, doc_link, alert_type)
    """
    # Extract error details
    error_type = error_data.get("detail", {}).get("error", "Unknown error")
    error_message = error_data.get("detail", {}).get("message", "")
    
    # Neo4j Cypher documentation base URL
    CYPHER_DOCS = "https://neo4j.com/docs/cypher-manual/current/"
    
    # Parse and categorize errors
    if status_code == 400:
        # Validation errors
        if "write operation" in error_message.lower() or "validation failed" in error_type.lower():
            return (
                "🚫 Write operations are not allowed",
                "Only read-only queries (MATCH, RETURN, WITH, etc.) are permitted for security reasons. Remove CREATE, MERGE, DELETE, SET, or similar keywords from your query.",
                f"{CYPHER_DOCS}clauses/match/",
                "danger"
            )
        elif "syntax error" in error_message.lower():
            # Extract the actual syntax error message
            return (
                "❌ Cypher Syntax Error",
                f"Your query has a syntax error: {error_message}. Check for missing parentheses, keywords, or commas.",
                f"{CYPHER_DOCS}syntax/",
                "danger"
            )
        else:
            return (
                "⚠️ Query Validation Error",
                error_message or "Your query did not pass validation. Check the query syntax and try again.",
                f"{CYPHER_DOCS}introduction/",
                "warning"
            )
    
    elif status_code == 500:
        # Server/execution errors
        if "unable to connect" in error_message.lower() or "connection" in error_message.lower():
            return (
                "🔌 Unable to Connect to Neo4j",
                f"Cannot establish connection to Neo4j database. Please ensure Neo4j is running at {settings.NEO4J_URI} and the credentials are correct.",
                "https://neo4j.com/docs/operations-manual/current/installation/",
                "danger"
            )
        elif "timeout" in error_message.lower():
            return (
                "⏱️ Query Timeout",
                "The query took too long to execute. Try simplifying your query or adding a LIMIT clause (e.g., LIMIT 100) to reduce the result set size.",
                f"{CYPHER_DOCS}clauses/limit/",
                "warning"
            )
        elif "syntax error" in error_message.lower():
            return (
                "❌ Cypher Syntax Error",
                f"{error_message}. Common issues: missing RETURN clause, unmatched parentheses, or invalid property access.",
                f"{CYPHER_DOCS}syntax/",
                "danger"
            )
        elif "not enabled" in error_message.lower():
            return (
                "⚙️ Neo4j Not Enabled",
                "Neo4j integration is not enabled in the application configuration. Contact your administrator.",
                None,
                "warning"
            )
        else:
            return (
                "💥 Query Execution Failed",
                f"{error_message or 'An error occurred while executing your query. Check the query syntax and Neo4j connection.'}",
                f"{CYPHER_DOCS}introduction/",
                "danger"
            )
    
    elif status_code == 503:
        # Service unavailable
        return (
            "🚧 Service Unavailable",
            "The Neo4j service is currently unavailable. Please try again later or contact your administrator.",
            None,
            "warning"
        )
    
    else:
        # Other errors
        return (
            "⚠️ Unexpected Error",
            error_message or "An unexpected error occurred. Please try again or contact support if the issue persists.",
            None,
            "danger"
        )


def _create_error_alert(message, alert_type='danger', hint=None, heading="Query Execution Failed", doc_link=None):
    """Create an error/warning alert component
    
    Args:
        message (str): Main error message
        alert_type (str): Bootstrap alert type ('danger', 'warning', 'info')
        hint (str, optional): Additional hint text
        heading (str, optional): Alert heading
        doc_link (str, optional): URL to documentation for more help
    
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
            html.P(message, className="mb-1", style={"fontSize": "14px"}),
            html.Small(hint, className="text-muted d-block mb-2", style={"fontSize": "12px"}) if hint else None
        ]
        
        # Add documentation link if provided
        if doc_link:
            alert_content.append(
                html.Hr(style={"margin": "8px 0"})
            )
            alert_content.append(
                html.Small([
                    html.I(className="fas fa-book me-1", style={"fontSize": "10px"}),
                    html.A(
                        "View Neo4j Documentation →",
                        href=doc_link,
                        target="_blank",
                        style={"fontSize": "12px", "color": "inherit", "textDecoration": "underline"}
                    )
                ])
            )
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


def _create_performance_metrics(node_count, rel_count, execution_time_ms, is_graph=True):
    """Create performance metrics display
    
    Args:
        node_count (int): Number of nodes (or result count for tabular)
        rel_count (int): Number of relationships (0 for tabular)
        execution_time_ms (float): Query execution time in milliseconds
        is_graph (bool): Whether this is a graph query or tabular query
    
    Returns:
        html.Div: Performance metrics component
    """
    # Determine performance status based on result count and execution time
    total_elements = node_count + rel_count if is_graph else node_count
    
    if is_graph:
        # For graph queries: warn if >100 nodes or >2 seconds
        if total_elements > 200 or execution_time_ms > 3000:
            status_color = "#dc3545"  # Red (danger)
            status_icon = "fa-exclamation-triangle"
            status_text = "Slow"
        elif total_elements > 100 or execution_time_ms > 2000:
            status_color = "#ffc107"  # Yellow (warning)
            status_icon = "fa-exclamation-circle"
            status_text = "OK"
        else:
            status_color = "#28a745"  # Green (success)
            status_icon = "fa-check-circle"
            status_text = "Fast"
    else:
        # For tabular queries: warn if >500 rows or >2 seconds
        if total_elements > 1000 or execution_time_ms > 3000:
            status_color = "#dc3545"  # Red
            status_icon = "fa-exclamation-triangle"
            status_text = "Slow"
        elif total_elements > 500 or execution_time_ms > 2000:
            status_color = "#ffc107"  # Yellow
            status_icon = "fa-exclamation-circle"
            status_text = "OK"
        else:
            status_color = "#28a745"  # Green
            status_icon = "fa-check-circle"
            status_text = "Fast"
    
    # Format execution time
    if execution_time_ms < 1000:
        time_display = f"{execution_time_ms:.0f}ms"
    else:
        time_display = f"{execution_time_ms/1000:.2f}s"
    
    metrics = [
        html.Div([
            html.I(className="fas fa-clock me-1", style={"color": "#6c757d", "fontSize": "10px"}),
            html.Span("Time: ", style={"color": "#6c757d", "fontSize": "11px", "fontWeight": "500"}),
            html.Span(time_display, style={"color": "#212529", "fontSize": "11px", "fontWeight": "600"})
        ], style={"display": "inline-block", "marginRight": "16px"})
    ]
    
    if is_graph:
        metrics.append(html.Div([
            html.I(className="fas fa-circle me-1", style={"color": "#6c757d", "fontSize": "8px"}),
            html.Span("Nodes: ", style={"color": "#6c757d", "fontSize": "11px", "fontWeight": "500"}),
            html.Span(str(node_count), style={"color": "#212529", "fontSize": "11px", "fontWeight": "600"})
        ], style={"display": "inline-block", "marginRight": "16px"}))
        
        metrics.append(html.Div([
            html.I(className="fas fa-arrow-right me-1", style={"color": "#6c757d", "fontSize": "8px"}),
            html.Span("Edges: ", style={"color": "#6c757d", "fontSize": "11px", "fontWeight": "500"}),
            html.Span(str(rel_count), style={"color": "#212529", "fontSize": "11px", "fontWeight": "600"})
        ], style={"display": "inline-block", "marginRight": "16px"}))
    else:
        metrics.append(html.Div([
            html.I(className="fas fa-table me-1", style={"color": "#6c757d", "fontSize": "8px"}),
            html.Span("Rows: ", style={"color": "#6c757d", "fontSize": "11px", "fontWeight": "500"}),
            html.Span(str(node_count), style={"color": "#212529", "fontSize": "11px", "fontWeight": "600"})
        ], style={"display": "inline-block", "marginRight": "16px"}))
    
    # Performance status indicator
    metrics.append(html.Div([
        html.I(className=f"fas {status_icon} me-1", style={"color": status_color, "fontSize": "10px"}),
        html.Span("Status: ", style={"color": "#6c757d", "fontSize": "11px", "fontWeight": "500"}),
        html.Span(status_text, style={"color": status_color, "fontSize": "11px", "fontWeight": "600"})
    ], style={"display": "inline-block"}))
    
    # Performance tip for slow queries
    tip = None
    if is_graph and total_elements > 100:
        tip = html.Small([
            html.I(className="fas fa-lightbulb me-1", style={"fontSize": "9px"}),
            f"Tip: Consider adding LIMIT 100 to reduce the number of elements ({total_elements} currently)."
        ], className="text-warning", style={"fontSize": "10px", "display": "block", "marginTop": "4px"})
    elif not is_graph and total_elements > 500:
        tip = html.Small([
            html.I(className="fas fa-lightbulb me-1", style={"fontSize": "9px"}),
            f"Tip: Consider adding LIMIT clause to reduce the number of rows ({total_elements} currently)."
        ], className="text-warning", style={"fontSize": "10px", "display": "block", "marginTop": "4px"})
    
    return html.Div([
        html.Div(metrics, style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"}),
        tip if tip else None
    ], style={
        "backgroundColor": "#f8f9fa",
        "borderRadius": "4px",
        "padding": "8px 12px",
        "marginBottom": "8px",
        "border": "1px solid #e9ecef"
    })


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


# Clientside callback to fit graph to screen when button clicked
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
        return window.dash_clientside.no_update;
    }
    """,
    Output("graph-fit-btn", "className"),  # Dummy output
    Input("graph-fit-btn", "n_clicks"),
    prevent_initial_call=True
)


# Clientside callback to fit graph when triggered programmatically (e.g., keyboard shortcuts)
clientside_callback(
    """
    function(trigger_value) {
        if (trigger_value) {
            // Get the Cytoscape instance
            const elem = document.getElementById('graph-cytoscape');
            if (elem && elem._cyreg && elem._cyreg.cy) {
                // Call fit() to zoom/pan to show all elements
                elem._cyreg.cy.fit(null, 30);  // 30px padding
            }
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("graph-fit-trigger", "className"),  # Dummy output
    Input("graph-fit-trigger", "children"),
    prevent_initial_call=True
)


# Callback for full-width toggle
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
            "Consider adding ",
            html.Code("LIMIT 100", style={"fontSize": "12px", "backgroundColor": "rgba(255,255,255,0.3)", "padding": "2px 6px"}),
            " to improve query performance and avoid loading too many nodes."
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
     Output("graph-details-panel", "style"),
     Output("graph-performance-metrics", "children"),
     Output("graph-performance-metrics", "style")],
    [Input("graph-execute-btn", "n_clicks")],
    [State("graph-query-input", "value")],
    prevent_initial_call=True
)
def execute_query(_n_clicks, query_text):
    """Execute Cypher query and display results"""
    import time
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
        return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style, None, hide_style
    
    # Get API base URL
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    # Track execution time
    start_time = time.time()
    
    try:
        # Send query to API
        response = requests.post(
            f"{api_base}/api/v1/graph/query",
            json={"query": query_text},
            timeout=TIMEOUT_SECONDS
        )
        
        # Calculate execution time in milliseconds
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Handle error responses
        if response.status_code != 200:
            error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
            
            # Parse error and get user-friendly message
            heading, hint, doc_link, alert_type = _parse_error_response(error_data, response.status_code)
            
            error_display = _create_error_alert(
                "",  # message is in heading for parsed errors
                alert_type=alert_type,
                hint=hint,
                heading=heading,
                doc_link=doc_link
            )
            return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style, None, hide_style
        
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
            performance_metrics = _create_performance_metrics(node_count, rel_count, execution_time_ms, is_graph=True)
            
            # Show graph, hide table and default, show details panel
            return (
                data,
                cyto_elements,
                show_style,
                success_alert,
                show_style,
                None,
                hide_style,
                panel_visible_style,  # Show details panel for graph results
                performance_metrics,
                show_style  # Show performance metrics
            )
        else:
            # Tabular results - create table
            raw_results = data.get("rawResults", [])
            table_display = _create_table_display(raw_results, result_count)
            performance_metrics = _create_performance_metrics(result_count, 0, execution_time_ms, is_graph=False)
            
            # Show table, hide graph and default, hide details panel
            return (
                data,
                empty_elements,
                hide_style,
                table_display,
                show_style,
                None,
                hide_style,
                hide_style,  # Hide details panel for tabular results
                performance_metrics,
                show_style  # Show performance metrics
            )
        
    except requests.exceptions.Timeout:
        error_display = _create_error_alert(
            "",
            alert_type='warning',
            heading=f"⏱️ Request Timeout ({TIMEOUT_SECONDS}s)",
            hint=f"The request to the backend API took longer than {TIMEOUT_SECONDS} seconds. Your query might be too complex or the database is slow. Try adding LIMIT 100 to reduce the result set.",
            doc_link="https://neo4j.com/docs/cypher-manual/current/clauses/limit/"
        )
        return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style, None, hide_style
    
    except requests.exceptions.ConnectionError:
        api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        error_display = _create_error_alert(
            "",
            alert_type='danger',
            heading="🔌 Backend API Connection Failed",
            hint=f"Unable to connect to the backend API at {api_url}. Please ensure the FastAPI server is running using 'uvicorn app.main:app --reload'.",
            doc_link=None
        )
        return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style, None, hide_style
    
    except requests.exceptions.HTTPError as e:
        error_display = _create_error_alert(
            "",
            alert_type='danger',
            heading="⚠️ HTTP Error",
            hint=f"An HTTP error occurred: {str(e)}. This usually indicates a server-side issue. Check the backend logs for more details.",
            doc_link=None
        )
        return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style, None, hide_style
    
    except Exception as e:
        error_display = _create_error_alert(
            "",
            alert_type='danger',
            heading="💥 Unexpected Error",
            hint=f"An unexpected error occurred: {str(e)}. Please try again or contact support if the issue persists.",
            doc_link=None
        )
        return None, empty_elements, hide_style, None, hide_style, error_display, default_container_style, hide_style, None, hide_style


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


# ==================== Phase 1.1c: Double-Click Expansion ====================

# Clientside callback to capture double-click events on nodes
# This sets up a persistent event listener on the Cytoscape instance
clientside_callback(
    """
    function(elements) {
        // Get the Cytoscape instance
        const elem = document.getElementById('graph-cytoscape');
        if (!elem || !elem._cyreg || !elem._cyreg.cy) {
            return window.dash_clientside.no_update;
        }
        
        const cy = elem._cyreg.cy;
        
        // Check if we've already attached the listener (avoid duplicates)
        if (!cy._dbltapListenerAttached) {
            cy.on('dbltap', 'node', function(evt) {
                const node = evt.target;
                const nodeId = node.id();
                
                // Create data object with node ID and timestamp
                const data = {
                    node_id: nodeId,
                    timestamp: Date.now()
                };
                
                // Update the store using Dash's set_props
                if (window.dash_clientside && window.dash_clientside.set_props) {
                    window.dash_clientside.set_props('doubleclicked-node-store', { data: data });
                }
            });
            
            // Mark that we've attached the listener
            cy._dbltapListenerAttached = true;
            console.log('[Phase 1.1c] Double-click event listener attached to Cytoscape');
        }
        
        return window.dash_clientside.no_update;
    }
    """,
    Output("doubleclicked-node-store", "data"),
    Input("graph-cytoscape", "elements"),
    prevent_initial_call=False
)


# ==================== Phase 1.1d: Right-Click Context Menu ====================

# Clientside callback to capture right-click events on nodes
# Captures node ID and mouse coordinates for menu positioning
clientside_callback(
    """
    function(elements) {
        // Get the Cytoscape instance
        const elem = document.getElementById('graph-cytoscape');
        if (!elem || !elem._cyreg || !elem._cyreg.cy) {
            return window.dash_clientside.no_update;
        }
        
        const cy = elem._cyreg.cy;
        
        // Check if we've already attached the listener (avoid duplicates)
        if (!cy._cxttapListenerAttached) {
            cy.on('cxttap', 'node', function(evt) {
                // Prevent default browser context menu
                evt.originalEvent.preventDefault();
                
                const node = evt.target;
                const nodeId = node.id();
                
                // Get mouse coordinates from the original event
                const x = evt.originalEvent.clientX;
                const y = evt.originalEvent.clientY;
                
                // Create data object with node ID, coordinates, and timestamp
                const data = {
                    node_id: nodeId,
                    x: x,
                    y: y,
                    timestamp: Date.now()
                };
                
                // Update the store using Dash's set_props
                if (window.dash_clientside && window.dash_clientside.set_props) {
                    window.dash_clientside.set_props('rightclicked-node-store', { data: data });
                }
            });
            
            // Also prevent default browser context menu on the container
            const container = elem.parentElement;
            if (container) {
                container.addEventListener('contextmenu', function(e) {
                    // Only prevent if the click is on a node (handled by cytoscape)
                    // Let background right-clicks through for now
                    if (e.target === elem || elem.contains(e.target)) {
                        e.preventDefault();
                    }
                });
            }
            
            // Mark that we've attached the listener
            cy._cxttapListenerAttached = true;
            console.log('[Phase 1.1d] Right-click event listener attached to Cytoscape');
        }
        
        return window.dash_clientside.no_update;
    }
    """,
    Output("rightclicked-node-store", "data"),
    Input("graph-cytoscape", "elements"),
    prevent_initial_call=False
)


# Python callback for double-click expansion with debouncing
@callback(
    [Output("graph-cytoscape", "elements", allow_duplicate=True),
     Output("expanded-nodes", "data", allow_duplicate=True),
     Output("loaded-node-ids", "data", allow_duplicate=True),
     Output("expansion-debounce-store", "data", allow_duplicate=True),
     Output("graph-table-container", "children", allow_duplicate=True),
     Output("graph-table-container", "style", allow_duplicate=True),
     Output("graph-layout-selector", "value", allow_duplicate=True)],
    Input("doubleclicked-node-store", "data"),
    [State("graph-cytoscape", "elements"),
     State("loaded-node-ids", "data"),
     State("expanded-nodes", "data"),
     State("expansion-debounce-store", "data"),
     State("graph-layout-selector", "value")],
    prevent_initial_call=True
)
def execute_doubleclick_expansion(dblclick_data, current_elements, loaded_node_ids, 
                                   expanded_nodes, debounce_store, current_layout):
    """Execute immediate expansion on double-click with default parameters"""
    show_style = {"display": "block"}
    hide_style = {"display": "none"}
    
    # Extract node_id from the store data
    if not dblclick_data or not isinstance(dblclick_data, dict):
        return (current_elements, expanded_nodes, loaded_node_ids, debounce_store,
                None, hide_style, current_layout)
    
    node_id = dblclick_data.get("node_id")
    timestamp = dblclick_data.get("timestamp", 0)
    
    if not node_id:
        return (current_elements, expanded_nodes, loaded_node_ids, debounce_store,
                None, hide_style, current_layout)
    
    # Debouncing: Check if this node was recently expanded (within 500ms)
    debounce_store = debounce_store or {}
    last_expansion_time = debounce_store.get(node_id, 0)
    time_since_last = timestamp - last_expansion_time
    
    DEBOUNCE_MS = 500  # 500ms debounce window
    if time_since_last < DEBOUNCE_MS:
        # Too soon, ignore this double-click
        return (current_elements, expanded_nodes, loaded_node_ids, debounce_store,
                None, hide_style, current_layout)
    
    # Update debounce store
    updated_debounce = debounce_store.copy()
    updated_debounce[node_id] = timestamp
    
    try:
        # Use default parameters for double-click expansion
        direction = "both"
        limit = 50
        
        # Prepare request payload
        exclude_ids = loaded_node_ids if loaded_node_ids else []
        payload = {
            "node_id": node_id,
            "direction": direction,
            "limit": limit,
            "offset": 0,
            "exclude_node_ids": exclude_ids,
            "relationship_types": None
        }
        
        # Call backend API
        api_url = "http://localhost:8000/api/v1/graph/expand"
        response = requests.post(api_url, json=payload, timeout=TIMEOUT_SECONDS)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract new nodes and relationships
            new_nodes = data.get("nodes", [])
            new_relationships = data.get("relationships", [])
            pagination = data.get("pagination", {})
            
            # Transform to Cytoscape format
            new_elements = neo4j_to_cytoscape({"nodes": new_nodes, "relationships": new_relationships})
            
            # Merge with existing elements (deduplicate by ID)
            existing_ids = {elem['data']['id'] for elem in current_elements}
            merged_elements = current_elements.copy()
            
            new_count = 0
            for elem in new_elements:
                elem_id = elem['data']['id']
                if elem_id not in existing_ids:
                    merged_elements.append(elem)
                    existing_ids.add(elem_id)
                    new_count += 1
            
            # Update loaded node IDs
            new_node_ids = [node['id'] for node in new_nodes]
            updated_loaded_ids = list(set(loaded_node_ids + new_node_ids)) if loaded_node_ids else new_node_ids
            
            # Update expanded nodes tracking
            updated_expanded = expanded_nodes.copy() if expanded_nodes else {}
            updated_expanded[node_id] = {
                "direction": direction,
                "count": len(new_nodes),
                "timestamp": datetime.now().isoformat()
            }
            
            # Edge case: No new neighbors found
            if len(new_nodes) == 0:
                info_msg = dbc.Alert([
                    html.I(className="fas fa-info-circle me-2"),
                    "No new neighbors found. Node may have no connections or all neighbors already loaded."
                ], color="info", className="mb-0", dismissable=True, duration=4000)
                return (current_elements, updated_expanded, loaded_node_ids, updated_debounce,
                       info_msg, show_style, current_layout)
            
            # Success message
            has_more = pagination.get("has_more", False)
            more_msg = " (More available)" if has_more else ""
            success_msg = dbc.Alert([
                html.I(className="fas fa-bolt me-2"),
                f"Double-click expansion: Loaded {len(new_nodes)} new nodes, {len(new_relationships)} new relationships{more_msg}"
            ], color="info", className="mb-0", dismissable=True, duration=3000)
            
            # Return updated data
            return (merged_elements, updated_expanded, updated_loaded_ids, updated_debounce,
                   success_msg, show_style, current_layout)
            
        else:
            # Handle error response
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("detail", {}).get("message", "Unknown error")
            
            error_alert = dbc.Alert([
                html.I(className="fas fa-exclamation-circle me-2"),
                f"Double-click expansion failed: {error_msg}"
            ], color="danger", className="mb-0", dismissable=True)
            return (current_elements, expanded_nodes, loaded_node_ids, updated_debounce,
                   error_alert, show_style, current_layout)
            
    except requests.exceptions.Timeout:
        error_alert = dbc.Alert([
            html.I(className="fas fa-clock me-2"),
            "Double-click expansion timed out"
        ], color="warning", className="mb-0", dismissable=True)
        return (current_elements, expanded_nodes, loaded_node_ids, updated_debounce,
               error_alert, show_style, current_layout)
    
    except requests.exceptions.ConnectionError:
        error_alert = dbc.Alert([
            html.I(className="fas fa-plug me-2"),
            "Could not connect to server. Please check your connection."
        ], color="danger", className="mb-0", dismissable=True)
        return (current_elements, expanded_nodes, loaded_node_ids, updated_debounce,
               error_alert, show_style, current_layout)
        
    except Exception as e:
        error_alert = dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            f"Double-click expansion error: {str(e)}"
        ], color="danger", className="mb-0", dismissable=True)
        return (current_elements, expanded_nodes, loaded_node_ids, updated_debounce,
               error_alert, show_style, current_layout)


# Callback to show context menu on right-click
@callback(
    Output("context-menu", "style"),
    Input("rightclicked-node-store", "data"),
    State("context-menu", "style"),
    prevent_initial_call=True
)
def show_context_menu(rightclick_data, current_menu_style):
    """Show context menu at mouse position when node is right-clicked"""
    if not rightclick_data or not isinstance(rightclick_data, dict):
        return current_menu_style
    
    x = rightclick_data.get("x", 0)
    y = rightclick_data.get("y", 0)
    
    # Update menu style to show it at the click position
    menu_style = current_menu_style.copy()
    menu_style["display"] = "block"
    menu_style["left"] = f"{x}px"
    menu_style["top"] = f"{y}px"
    
    return menu_style


# Callback to handle "Expand Node..." menu item - opens modal
@callback(
    [Output("expansion-modal", "is_open", allow_duplicate=True),
     Output("selected-node-for-expansion", "data", allow_duplicate=True),
     Output("context-menu", "style", allow_duplicate=True)],
    Input("ctx-menu-expand", "n_clicks"),
    [State("rightclicked-node-store", "data"),
     State("context-menu", "style")],
    prevent_initial_call=True
)
def context_menu_expand_modal(n_clicks, rightclick_data, menu_style):
    """Open expansion modal from context menu"""
    if not n_clicks or not rightclick_data:
        raise PreventUpdate
    
    node_id = rightclick_data.get("node_id")
    
    # Hide menu
    updated_menu_style = menu_style.copy()
    updated_menu_style["display"] = "none"
    
    return True, node_id, updated_menu_style


# Callback to handle quick expansion menu items (incoming/outgoing)
@callback(
    [Output("graph-cytoscape", "elements", allow_duplicate=True),
     Output("expanded-nodes", "data", allow_duplicate=True),
     Output("loaded-node-ids", "data", allow_duplicate=True),
     Output("context-menu", "style", allow_duplicate=True),
     Output("graph-table-container", "children", allow_duplicate=True),
     Output("graph-table-container", "style", allow_duplicate=True),
     Output("graph-layout-selector", "value", allow_duplicate=True)],
    [Input("ctx-menu-expand-incoming", "n_clicks"),
     Input("ctx-menu-expand-outgoing", "n_clicks")],
    [State("rightclicked-node-store", "data"),
     State("graph-cytoscape", "elements"),
     State("loaded-node-ids", "data"),
     State("expanded-nodes", "data"),
     State("context-menu", "style"),
     State("graph-layout-selector", "value")],
    prevent_initial_call=True
)
def context_menu_quick_expand(n_clicks_incoming, n_clicks_outgoing, rightclick_data,
                              current_elements, loaded_node_ids, expanded_nodes, 
                              menu_style, current_layout):
    """Handle quick expansion from context menu"""
    show_style = {"display": "block"}
    hide_style = {"display": "none"}
    
    # Hide menu
    updated_menu_style = menu_style.copy()
    updated_menu_style["display"] = "none"
    
    if not rightclick_data:
        return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
                None, hide_style, current_layout)
    
    # Determine which button was clicked
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # Set direction based on button
    if button_id == "ctx-menu-expand-incoming":
        direction = "incoming"
    elif button_id == "ctx-menu-expand-outgoing":
        direction = "outgoing"
    else:
        raise PreventUpdate
    
    node_id = rightclick_data.get("node_id")
    if not node_id:
        return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
                None, hide_style, current_layout)
    
    try:
        # Use default limit for quick expansion
        limit = 50
        
        # Prepare request payload
        exclude_ids = loaded_node_ids if loaded_node_ids else []
        payload = {
            "node_id": node_id,
            "direction": direction,
            "limit": limit,
            "offset": 0,
            "exclude_node_ids": exclude_ids,
            "relationship_types": None
        }
        
        # Call backend API
        api_url = "http://localhost:8000/api/v1/graph/expand"
        response = requests.post(api_url, json=payload, timeout=TIMEOUT_SECONDS)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract new nodes and relationships
            new_nodes = data.get("nodes", [])
            new_relationships = data.get("relationships", [])
            pagination = data.get("pagination", {})
            
            # Transform to Cytoscape format
            new_elements = neo4j_to_cytoscape({"nodes": new_nodes, "relationships": new_relationships})
            
            # Merge with existing elements (deduplicate by ID)
            existing_ids = {elem['data']['id'] for elem in current_elements}
            merged_elements = current_elements.copy()
            
            new_count = 0
            for elem in new_elements:
                elem_id = elem['data']['id']
                if elem_id not in existing_ids:
                    merged_elements.append(elem)
                    existing_ids.add(elem_id)
                    new_count += 1
            
            # Update loaded node IDs
            new_node_ids = [node['id'] for node in new_nodes]
            updated_loaded_ids = list(set(loaded_node_ids + new_node_ids)) if loaded_node_ids else new_node_ids
            
            # Update expanded nodes tracking
            updated_expanded = expanded_nodes.copy() if expanded_nodes else {}
            updated_expanded[node_id] = {
                "direction": direction,
                "count": len(new_nodes),
                "timestamp": datetime.now().isoformat()
            }
            
            # Edge case: No new neighbors found
            if len(new_nodes) == 0:
                direction_label = "Incoming" if direction == "incoming" else "Outgoing"
                info_msg = dbc.Alert([
                    html.I(className="fas fa-info-circle me-2"),
                    f"No new {direction_label.lower()} neighbors found."
                ], color="info", className="mb-0", dismissable=True, duration=4000)
                return (merged_elements, updated_expanded, updated_loaded_ids, updated_menu_style,
                       info_msg, show_style, current_layout)
            
            # Success message
            direction_label = "Incoming" if direction == "incoming" else "Outgoing"
            has_more = pagination.get("has_more", False)
            more_msg = " (More available)" if has_more else ""
            success_msg = dbc.Alert([
                html.I(className="fas fa-context-menu me-2"),
                f"{direction_label} expansion: Loaded {len(new_nodes)} new nodes, {len(new_relationships)} new relationships{more_msg}"
            ], color="success", className="mb-0", dismissable=True, duration=3000)
            
            # Return updated data
            return (merged_elements, updated_expanded, updated_loaded_ids, updated_menu_style,
                   success_msg, show_style, current_layout)
            
        else:
            # Handle error response
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("detail", {}).get("message", "Unknown error")
            
            error_alert = dbc.Alert([
                html.I(className="fas fa-exclamation-circle me-2"),
                f"Quick expansion failed: {error_msg}"
            ], color="danger", className="mb-0", dismissable=True)
            return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
                   error_alert, show_style, current_layout)
            
    except requests.exceptions.Timeout:
        error_alert = dbc.Alert([
            html.I(className="fas fa-clock me-2"),
            "Quick expansion timed out"
        ], color="warning", className="mb-0", dismissable=True)
        return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
               error_alert, show_style, current_layout)
    
    except requests.exceptions.ConnectionError:
        error_alert = dbc.Alert([
            html.I(className="fas fa-plug me-2"),
            "Could not connect to server. Please check your connection."
        ], color="danger", className="mb-0", dismissable=True)
        return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
               error_alert, show_style, current_layout)
    
    except Exception as e:
        error_alert = dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            f"Quick expansion error: {str(e)}"
        ], color="danger", className="mb-0", dismissable=True)
        return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
               error_alert, show_style, current_layout)


# Clientside callback to copy node ID to clipboard
clientside_callback(
    """
    function(n_clicks, rightclick_data) {
        if (n_clicks && rightclick_data && rightclick_data.node_id) {
            // Copy to clipboard
            if (navigator.clipboard) {
                navigator.clipboard.writeText(rightclick_data.node_id);
                console.log('Copied node ID:', rightclick_data.node_id);
            }
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("ctx-menu-copy-id", "title"),
    Input("ctx-menu-copy-id", "n_clicks"),
    State("rightclicked-node-store", "data"),
    prevent_initial_call=True
)


# Callback to hide context menu after copy
@callback(
    Output("context-menu", "style", allow_duplicate=True),
    Input("ctx-menu-copy-id", "n_clicks"),
    State("context-menu", "style"),
    prevent_initial_call=True
)
def hide_menu_after_copy(n_clicks, menu_style):
    """Hide menu after copying node ID"""
    if n_clicks:
        updated_style = menu_style.copy()
        updated_style["display"] = "none"
        return updated_style
    raise PreventUpdate


# Callback to handle "Remove from View" menu item
@callback(
    [Output("graph-cytoscape", "elements", allow_duplicate=True),
     Output("context-menu", "style", allow_duplicate=True),
     Output("graph-table-container", "children", allow_duplicate=True),
     Output("graph-table-container", "style", allow_duplicate=True)],
    Input("ctx-menu-remove", "n_clicks"),
    [State("rightclicked-node-store", "data"),
     State("graph-cytoscape", "elements"),
     State("context-menu", "style")],
    prevent_initial_call=True
)
def context_menu_remove_node(n_clicks, rightclick_data, current_elements, menu_style):
    """Remove node from view"""
    show_style = {"display": "block"}
    
    # Hide menu
    updated_menu_style = menu_style.copy()
    updated_menu_style["display"] = "none"
    
    if not n_clicks or not rightclick_data:
        raise PreventUpdate
    
    node_id = rightclick_data.get("node_id")
    if not node_id:
        return current_elements, updated_menu_style, None, {"display": "none"}
    
    # Remove node and its edges from elements
    filtered_elements = []
    removed_count = 0
    
    for elem in current_elements:
        elem_id = elem['data'].get('id')
        
        # Skip the node itself
        if elem_id == node_id:
            removed_count += 1
            continue
        
        # Skip edges connected to this node
        if 'source' in elem['data'] and 'target' in elem['data']:
            if elem['data']['source'] == node_id or elem['data']['target'] == node_id:
                removed_count += 1
                continue
        
        filtered_elements.append(elem)
    
    # Success message
    success_msg = dbc.Alert([
        html.I(className="fas fa-trash-alt me-2"),
        f"Removed node and {removed_count - 1} connected relationships from view"
    ], color="warning", className="mb-0", dismissable=True, duration=3000)
    
    return filtered_elements, updated_menu_style, success_msg, show_style


# Clientside callback to hide context menu on outside click
clientside_callback(
    """
    function(n_intervals) {
        // Add click listener to document to hide menu on outside click
        if (!window._contextMenuClickListenerAdded) {
            document.addEventListener('click', function(e) {
                const menu = document.getElementById('context-menu');
                if (menu && menu.style.display === 'block') {
                    // Check if click is outside the menu
                    if (!menu.contains(e.target)) {
                        menu.style.display = 'none';
                    }
                }
            });
            
            // Add hover effects to menu items
            const menuItems = document.querySelectorAll('.context-menu-item');
            menuItems.forEach(item => {
                item.addEventListener('mouseenter', function() {
                    this.style.backgroundColor = '#f0f0f0';
                });
                item.addEventListener('mouseleave', function() {
                    this.style.backgroundColor = 'transparent';
                });
            });
            
            window._contextMenuClickListenerAdded = true;
            console.log('[Phase 1.1d] Context menu click and hover listeners attached');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("context-menu", "className"),
    Input("graph-cytoscape", "elements"),
    prevent_initial_call=False
)


# ==================== Phase 1.1e: Keyboard Shortcuts ====================

# Clientside callback to capture keyboard shortcuts
clientside_callback(
    """
    function(elements) {
        // Only attach listener once
        if (!window._keyboardListenerAttached) {
            document.addEventListener('keydown', function(e) {
                // Ignore if user is typing in an input field
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                    return;
                }
                
                const key = e.key.toLowerCase();
                const timestamp = Date.now();
                
                // E key: Expand selected node
                if (key === 'e') {
                    e.preventDefault();
                    if (window.dash_clientside && window.dash_clientside.set_props) {
                        window.dash_clientside.set_props('keyboard-shortcut-store', {
                            data: { key: 'e', action: 'expand', timestamp: timestamp }
                        });
                    }
                }
                
                // F key: Fit graph to view
                else if (key === 'f') {
                    e.preventDefault();
                    if (window.dash_clientside && window.dash_clientside.set_props) {
                        window.dash_clientside.set_props('keyboard-shortcut-store', {
                            data: { key: 'f', action: 'fit', timestamp: timestamp }
                        });
                    }
                }
            });
            
            window._keyboardListenerAttached = true;
            console.log('[Phase 1.1e] Keyboard shortcuts listener attached (E = expand, F = fit)');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("keyboard-shortcut-store", "data"),
    Input("graph-cytoscape", "elements"),
    prevent_initial_call=False
)


# Python callback to handle keyboard shortcuts
@callback(
    [Output("expansion-modal", "is_open", allow_duplicate=True),
     Output("selected-node-for-expansion", "data", allow_duplicate=True),
     Output("graph-fit-trigger", "children", allow_duplicate=True)],
    Input("keyboard-shortcut-store", "data"),
    [State("graph-cytoscape", "selectedNodeData"),
     State("graph-fit-trigger", "children")],
    prevent_initial_call=True
)
def handle_keyboard_shortcuts(shortcut_data, selected_nodes, current_fit_count):
    """Handle keyboard shortcuts for expansion and navigation"""
    if not shortcut_data or not isinstance(shortcut_data, dict):
        raise PreventUpdate
    
    action = shortcut_data.get("action")
    
    # E key: Open expansion modal for selected node
    if action == "expand":
        if selected_nodes and len(selected_nodes) > 0:
            node_id = str(selected_nodes[0].get('id', ''))
            if node_id:
                # Open modal with selected node
                return True, node_id, current_fit_count or 0
        # No node selected - prevent update
        raise PreventUpdate
    
    # F key: Fit graph to view
    elif action == "fit":
        # Trigger fit by incrementing the counter
        new_count = (current_fit_count or 0) + 1
        return False, None, new_count
    
    raise PreventUpdate


# ==================== Phase 1.1b: Node Expansion Callbacks ====================


# ==================== Phase 1.1b: Node Expansion Callbacks ====================

# Callback to open expansion modal when "Expand Node" button clicked
@callback(
    [Output("expansion-modal", "is_open", allow_duplicate=True),
     Output("selected-node-for-expansion", "data")],
    Input("expand-node-btn", "n_clicks"),
    [State("graph-cytoscape", "selectedNodeData")],
    prevent_initial_call=True
)
def open_expansion_modal(n_clicks, selected_nodes):
    """Open the expansion modal and store the selected node ID"""
    if n_clicks and selected_nodes and len(selected_nodes) > 0:
        node_data = selected_nodes[0]
        node_id = node_data.get('id')
        return True, node_id
    return False, None


# Callback to close expansion modal when Cancel clicked
@callback(
    Output("expansion-modal", "is_open", allow_duplicate=True),
    Input("expansion-modal-cancel", "n_clicks"),
    prevent_initial_call=True
)
def close_expansion_modal(n_clicks):
    """Close the expansion modal"""
    if n_clicks:
        return False
    return True


# Callback to execute node expansion
@callback(
    [Output("graph-cytoscape", "elements", allow_duplicate=True),
     Output("expanded-nodes", "data", allow_duplicate=True),
     Output("loaded-node-ids", "data", allow_duplicate=True),
     Output("expansion-modal", "is_open", allow_duplicate=True),
     Output("graph-table-container", "children", allow_duplicate=True),
     Output("graph-table-container", "style", allow_duplicate=True),
     Output("graph-layout-selector", "value", allow_duplicate=True),
     Output("graph-fit-trigger", "children", allow_duplicate=True)],
    Input("expansion-modal-expand", "n_clicks"),
    [State("selected-node-for-expansion", "data"),
     State("expansion-direction-selector", "value"),
     State("expansion-limit-input", "value"),
     State("expansion-auto-fit-checkbox", "value"),
     State("graph-cytoscape", "elements"),
     State("loaded-node-ids", "data"),
     State("expanded-nodes", "data"),
     State("graph-layout-selector", "value"),
     State("graph-fit-trigger", "children")],
    prevent_initial_call=True
)
def execute_node_expansion(n_clicks, node_id, direction, limit, auto_fit, current_elements, 
                          loaded_node_ids, expanded_nodes, current_layout, current_fit_count):
    """Execute node expansion by calling backend API and merging results"""
    show_style = {"display": "block"}
    hide_style = {"display": "none"}
    fit_count = current_fit_count or 0
    
    if not n_clicks or not node_id:
        return current_elements, expanded_nodes, loaded_node_ids, True, None, hide_style, current_layout, fit_count
    
    try:
        # Prepare request payload
        exclude_ids = loaded_node_ids if loaded_node_ids else []
        payload = {
            "node_id": node_id,
            "direction": direction,
            "limit": limit,
            "offset": 0,
            "exclude_node_ids": exclude_ids,
            "relationship_types": None
        }
        
        # Call backend API
        api_url = "http://localhost:8000/api/v1/graph/expand"
        response = requests.post(api_url, json=payload, timeout=TIMEOUT_SECONDS)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract new nodes and relationships
            new_nodes = data.get("nodes", [])
            new_relationships = data.get("relationships", [])
            pagination = data.get("pagination", {})
            
            # Transform to Cytoscape format
            new_elements = neo4j_to_cytoscape({"nodes": new_nodes, "relationships": new_relationships})
            
            # Merge with existing elements (deduplicate by ID)
            existing_ids = {elem['data']['id'] for elem in current_elements}
            merged_elements = current_elements.copy()
            
            new_count = 0
            for elem in new_elements:
                elem_id = elem['data']['id']
                if elem_id not in existing_ids:
                    merged_elements.append(elem)
                    existing_ids.add(elem_id)
                    new_count += 1
            
            # Update loaded node IDs
            new_node_ids = [node['id'] for node in new_nodes]
            updated_loaded_ids = list(set(loaded_node_ids + new_node_ids)) if loaded_node_ids else new_node_ids
            
            # Update expanded nodes tracking
            updated_expanded = expanded_nodes.copy() if expanded_nodes else {}
            updated_expanded[node_id] = {
                "direction": direction,
                "count": len(new_nodes),
                "timestamp": datetime.now().isoformat()
            }
            
            # Edge case: No new neighbors found
            if len(new_nodes) == 0:
                info_msg = dbc.Alert([
                    html.I(className="fas fa-info-circle me-2"),
                    "No new neighbors found. Node may have no connections or all neighbors already loaded."
                ], color="info", className="mb-0", dismissable=True, duration=4000)
                # Close modal and return
                return current_elements, updated_expanded, loaded_node_ids, False, info_msg, show_style, current_layout, fit_count
            
            # Success message
            has_more = pagination.get("has_more", False)
            more_msg = " (More available)" if has_more else ""
            success_msg = dbc.Alert([
                html.I(className="fas fa-check-circle me-2"),
                f"Expansion complete! Loaded {len(new_nodes)} new nodes, {len(new_relationships)} new relationships{more_msg}"
            ], color="success", className="mb-0", dismissable=True, duration=4000)
            
            # Auto-fit if enabled
            if auto_fit:
                fit_count = fit_count + 1
            
            # Close modal and return updated data
            # Trigger layout re-run to accommodate new nodes
            return merged_elements, updated_expanded, updated_loaded_ids, False, success_msg, show_style, current_layout, fit_count
            
        else:
            # Handle error response
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("detail", {}).get("message", "Unknown error")
            
            error_alert = dbc.Alert([
                html.I(className="fas fa-exclamation-circle me-2"),
                f"Expansion failed: {error_msg}"
            ], color="danger", className="mb-0", dismissable=True)
            return current_elements, expanded_nodes, loaded_node_ids, True, error_alert, show_style, current_layout, fit_count
            
    except requests.exceptions.Timeout:
        error_alert = dbc.Alert([
            html.I(className="fas fa-clock me-2"),
            "Request timed out. The expansion took too long."
        ], color="warning", className="mb-0", dismissable=True)
        return current_elements, expanded_nodes, loaded_node_ids, True, error_alert, show_style, current_layout, fit_count
    
    except requests.exceptions.ConnectionError:
        error_alert = dbc.Alert([
            html.I(className="fas fa-plug me-2"),
            "Could not connect to server. Please check your connection."
        ], color="danger", className="mb-0", dismissable=True)
        return current_elements, expanded_nodes, loaded_node_ids, True, error_alert, show_style, current_layout, fit_count
        
    except Exception as e:
        error_alert = dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            f"Error: {str(e)}"
        ], color="danger", className="mb-0", dismissable=True)
        return current_elements, expanded_nodes, loaded_node_ids, True, error_alert, show_style, current_layout, fit_count
