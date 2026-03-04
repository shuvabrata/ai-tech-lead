"""Graph page layout builder

This module constructs the complete UI layout for the graph visualization page,
broken down into logical sections for maintainability.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto

from .styles import CYTOSCAPE_STYLESHEET
from .components import create_expansion_modal, create_context_menu

from app.dash_app.components.common import create_page_header
from app.dash_app.styles import (
    FONT_SANS,
    FONT_WEIGHT_SEMIBOLD,
    COLOR_GRAY_DARK,
    COLOR_GRAY_LIGHTER,
    SPACING_XXSMALL,
    GRAPH_SECTION_CONTAINER_STYLE,
    GRAPH_SECTION_TITLE_STYLE,
    GRAPH_QUERY_TEXTAREA_STYLE,
    GRAPH_EXECUTE_BUTTON_STYLE,
    GRAPH_HELPER_TEXT_STYLE,
    GRAPH_QUERY_SECTION_CONTAINER_STYLE,
    GRAPH_CYTOSCAPE_STYLE,
    GRAPH_EMPTY_STATE_ICON_STYLE,
    GRAPH_EMPTY_STATE_TEXT_STYLE,
    GRAPH_DETAILS_PANEL_STYLE,
    GRAPH_DETAILS_PANEL_ICON_STYLE,
    GRAPH_LOADING_COLOR
)


def create_graph_controls():
    """Create layout controls (layout selector and action buttons)
    
    Returns:
        dbc.Row containing layout selector and control buttons
    """
    return dbc.Row([
        dbc.Col([
            html.Label(
                "Layout:",
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": "11px",
                    "fontWeight": FONT_WEIGHT_SEMIBOLD,
                    "color": COLOR_GRAY_DARK,
                    "marginRight": SPACING_XXSMALL,
                    "textTransform": "uppercase",
                    "letterSpacing": "0.3px"
                }
            ),
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
                style={
                    "fontFamily": FONT_SANS,
                    "width": "200px",
                    "display": "inline-block",
                    "fontSize": "12px",
                    "border": f"1px solid {COLOR_GRAY_LIGHTER}",
                    "borderRadius": "2px"
                },
                size="sm"
            )
        ], width="auto"),
        dbc.Col([
            dbc.ButtonGroup([
                dbc.Button(
                    "Fit",
                    id="graph-fit-btn",
                    outline=True,
                    color="secondary",
                    size="sm",
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": "11px",
                        "padding": "4px 12px",
                        "borderRadius": "2px",
                        "borderColor": COLOR_GRAY_LIGHTER,
                        "color": COLOR_GRAY_DARK
                    }
                ),
                dbc.Button(
                    "Reset",
                    id="graph-reset-btn",
                    outline=True,
                    color="secondary",
                    size="sm",
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": "11px",
                        "padding": "4px 12px",
                        "borderRadius": "2px",
                        "borderColor": COLOR_GRAY_LIGHTER,
                        "color": COLOR_GRAY_DARK
                    }
                ),
                dbc.Button(
                    "Full",
                    id="graph-fullwidth-btn",
                    outline=True,
                    color="secondary",
                    size="sm",
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": "11px",
                        "padding": "4px 12px",
                        "borderRadius": "2px",
                        "borderColor": COLOR_GRAY_LIGHTER,
                        "color": COLOR_GRAY_DARK
                    }
                )
            ], size="sm")
        ], width="auto", className="ms-auto")
    ], className="mb-2", align="center")


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
                style=GRAPH_CYTOSCAPE_STYLE,
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
            "padding": "16px"
        },
        children=[
            html.Div(
                [
                    html.Div(
                        "◆",
                        style=GRAPH_EMPTY_STATE_ICON_STYLE
                    ),
                    html.P(
                        "No results to display. Execute a query to visualize network relationships.",
                        style=GRAPH_EMPTY_STATE_TEXT_STYLE
                    )
                ],
                className="text-center",
                style={"marginTop": "80px"}
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
            style=GRAPH_DETAILS_PANEL_STYLE,
            children=[
                html.Div([
                    html.I(className="fas fa-info-circle fa-lg mb-2", style=GRAPH_DETAILS_PANEL_ICON_STYLE),
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
            color=GRAPH_LOADING_COLOR,
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
    ], style=GRAPH_SECTION_CONTAINER_STYLE)


def create_query_input_section():
    """Create query input section with textarea and execute button
    
    Returns:
        html.Div containing query input controls
    """
    return html.Div([
        html.Div(
            "Query Console",
            style=GRAPH_SECTION_TITLE_STYLE
        ),
        
        # Row with textarea and execute button side by side
        dbc.Row([
            dbc.Col([
                dbc.Textarea(
                    id="graph-query-input",
                    placeholder="MATCH (n:Project)-[r]->(m)\nRETURN n, r, m\nLIMIT 10",
                    style=GRAPH_QUERY_TEXTAREA_STYLE,
                    className="graph-query-input"
                )
            ], width=10),
            dbc.Col([
                dbc.Button(
                    "Execute",
                    id="graph-execute-btn",
                    style=GRAPH_EXECUTE_BUTTON_STYLE,
                    className="graph-execute-btn"
                ),
            ], width=2, className="d-flex align-items-start")
        ], className="mb-2 g-3"),
        
        # Validation message container
        html.Div(id="query-validation-message", className="mb-2"),
        
        # Helper text
        html.Div([
            html.Small(
                "Ctrl+Enter to execute • Read-only queries only",
                style=GRAPH_HELPER_TEXT_STYLE
            )
        ])
    ], style=GRAPH_QUERY_SECTION_CONTAINER_STYLE)


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
    """Build complete graph page layout with Executive Dashboard aesthetic
    
    Returns:
        html.Div with full page layout
    """
    return html.Div([
        # Page header
        create_page_header("Relationship Mapping & Network Visualization"),
        
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
    ], className="mt-3")
