"""Graph page layout builder

This module constructs the complete UI layout for the graph visualization page,
broken down into logical sections for maintainability.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto

from .styles import CYTOSCAPE_STYLESHEET
from .components import create_expansion_modal, create_context_menu


def create_graph_controls():
    """Create layout controls (layout selector and action buttons)
    
    Returns:
        dbc.Row containing layout selector and control buttons
    """
    return dbc.Row([
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
                value="circle",
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
    ], className="mb-1", align="center")


def create_graph_container():
    """Create main graph visualization container with Cytoscape
    
    Returns:
        html.Div containing Cytoscape graph component
    """
    return html.Div(
        id="graph-cytoscape-container",
        style={"display": "none"},  # Hidden by default
        children=[
            create_graph_controls(),
            
            cyto.Cytoscape(
                id="graph-cytoscape",
                elements=[],
                layout={'name': 'circle', 'animate': True},
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
    )


def create_table_container():
    """Create container for tabular query results
    
    Returns:
        html.Div for displaying tables
    """
    return html.Div(
        id="graph-table-container",
        style={"display": "none"}  # Hidden by default
    )


def create_empty_state():
    """Create empty state display (shown before any query execution)
    
    Returns:
        html.Div with empty state message
    """
    return html.Div(
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


def create_details_panel():
    """Create property details panel for selected nodes/edges
    
    Returns:
        dbc.Col containing details panel
    """
    return dbc.Col([
        html.Div(
            id="graph-details-panel",
            style={
                "backgroundColor": "#f8f9fa",
                "borderRadius": "4px",
                "border": "1px solid #dee2e6",
                "padding": "8px",
                "height": "calc(70vh + 40px)",  # Match graph controls + cytoscape height
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


def create_results_section():
    """Create the results section (graph + details panel)
    
    Returns:
        html.Div containing the complete results section
    """
    return html.Div([
        dcc.Loading(
            id="graph-loading",
            type="circle",
            color="#0d6efd",
            children=[
                dbc.Row([
                    # Graph visualization area
                    dbc.Col([
                        create_graph_container(),
                        create_table_container(),
                        create_empty_state()
                    ], id="graph-viz-col", width=8),
                    
                    # Property details panel (collapsible)
                    create_details_panel()
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
    })


def create_query_input_section():
    """Create query input section with textarea and execute button
    
    Returns:
        html.Div containing query input controls
    """
    return html.Div([
        html.H6("Query", className="mb-1", style={"fontWeight": "500", "color": "#495057", "fontSize": "13px"}),
        
        # Row with textarea and execute button side by side
        dbc.Row([
            dbc.Col([
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
                    }
                )
            ], width=10),
            dbc.Col([
                dbc.Button(
                    [html.I(className="fas fa-play me-1"), "Execute"],
                    id="graph-execute-btn",
                    color="primary",
                    size="sm",
                    style={
                        "borderRadius": "6px",
                        "fontWeight": "500",
                        "fontSize": "13px",
                        "height": "90px",
                        "width": "100%"
                    }
                ),
            ], width=2, className="d-flex align-items-start")
        ], className="mb-1 g-2"),
        
        # Validation message container
        html.Div(id="query-validation-message", className="mb-1"),
        
        # Helper text
        html.Div([
            html.Small(
                "Ctrl+Enter to execute • Read-only queries only",
                className="text-muted",
                style={"fontSize": "11px"}
            )
        ], className="d-flex align-items-center")
    ], style={
        "backgroundColor": "#ffffff",
        "borderRadius": "4px",
        "border": "1px solid #e0e0e0",
        "padding": "8px",
        "boxShadow": "0 1px 2px rgba(0,0,0,0.05)"
    })


def create_stores():
    """Create all dcc.Store components for state management
    
    Returns:
        List of dcc.Store components
    """
    return [
        # Hidden data store for graph data
        dcc.Store(id="graph-data-store", data=None),
        
        # Session store for query history (optional, for future use)
        dcc.Store(id="graph-query-history", data=[]),
        
        # Store for details panel collapsed state
        dcc.Store(id="graph-fullwidth-state", data=False),
        
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
    ]


def create_hidden_elements():
    """Create hidden UI elements (triggers, etc.)
    
    Returns:
        List of hidden elements
    """
    return [
        # Performance metrics section (hidden by default, shown after query execution)
        html.Div(
            id="graph-performance-metrics",
            style={"display": "none"}
        ),
        
        # Hidden div for triggering fit-to-screen via clientside callback
        html.Div(id="graph-fit-trigger", style={"display": "none"}),
    ]


def get_layout():
    """Build complete graph page layout
    
    Returns:
        html.Div with full page layout
    """
    return html.Div([
        # Results Section (graph visualization + details panel)
        create_results_section(),
        
        # Query Input Section
        create_query_input_section(),
        
        # Hidden elements (performance metrics, triggers)
        *create_hidden_elements(),
        
        # State stores (hidden)
        *create_stores(),
        
        # Context menu
        create_context_menu(),
        
        # Expansion modal
        create_expansion_modal(),
    ])
