"""Graph page layout builder

This module constructs the complete UI layout for the graph visualization page,
broken down into logical sections for maintainability.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto

from .styles import CYTOSCAPE_STYLESHEET
from .components import create_expansion_modal, create_context_menu

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
    GRAPH_LOADING_COLOR,
    GRAPH_NODE_HOVER_TOOLTIP_STYLE,
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
                    {"label": "Manual Stable (preset)", "value": "preset"},
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
        style={"display": "none"},  # Hidden initially, then maintains consistent size after first query
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
                wheelSensitivity=1.0,
                minZoom=0.1,
                maxZoom=3
            )
        ]
    )


def create_filter_panel():
    """Create relationship filtering controls panel (Phase 1.2.4)
    
    Returns:
        html.Div containing collapsible filter controls
    """
    return html.Div([
        # Collapsible header (always visible)
        dbc.Button(
            [
                html.I(id="filter-collapse-icon", className="fas fa-chevron-right me-2"),
                "Filters"
            ],
            id="toggle-filter-collapse-btn",
            className="w-100 text-start graph-filter-toggle-btn",
            style={
                "fontSize": "13px",
                "fontWeight": "600",
                "color": COLOR_GRAY_DARK,
                "border": f"1px solid {COLOR_GRAY_LIGHTER}",
                "borderRadius": "4px",
                "backgroundColor": "var(--color-background-white)",
                "padding": "8px 12px",
                "marginBottom": "8px"
            }
        ),
        
        # Collapsible filter content
        dbc.Collapse(
            id="filter-panel-collapse",
            is_open=False,
            children=[
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Small(
                                    "Refining loaded graph",
                                    className="graph-filter-mode-label d-block"
                                ),
                                html.Small(
                                    id="filter-results-summary",
                                    children="Load a graph to refine it locally.",
                                    className="graph-filter-summary d-block"
                                )
                            ]),
                            dbc.Button(
                                "Clear All",
                                id="clear-filters-btn",
                                color="link",
                                size="sm",
                                className="ms-auto",
                                style={"fontSize": "11px", "padding": "0", "textDecoration": "none"}
                            )
                        ], className="d-flex justify-content-between align-items-start mb-3"),

                    html.Div(
                        id="filter-active-chips",
                        className="graph-filter-chip-list mb-3",
                        children=[
                            html.Span(
                                "No active filters",
                                className="graph-filter-empty-state"
                            )
                        ]
                    ),

                    html.Div([
                        html.Label(
                            "Display Filtered Items:",
                            style={
                                "fontSize": "11px",
                                "fontWeight": FONT_WEIGHT_SEMIBOLD,
                                "color": COLOR_GRAY_DARK,
                                "marginBottom": "8px",
                                "display": "block"
                            }
                        ),
                        dbc.RadioItems(
                            id="filter-display-mode",
                            options=[
                                {"label": "Hide", "value": "hide"},
                                {"label": "Dim", "value": "dim"}
                            ],
                            value="hide",
                            inline=True,
                            className="graph-filter-radio",
                            style={"fontSize": "12px"}
                        )
                    ], className="mb-3"),
                    
                    # Node Type Checkboxes
                    html.Div([
                        html.Label(
                            "Node Types:",
                            style={
                                "fontSize": "11px",
                                "fontWeight": FONT_WEIGHT_SEMIBOLD,
                                "color": COLOR_GRAY_DARK,
                                "marginBottom": "8px",
                                "display": "block"
                            }
                        ),
                        dbc.Checklist(
                            id="node-type-filter",
                            options=[],  # Populated dynamically
                            value=[],   # All selected by default
                            inline=False,
                            className="graph-filter-checklist",
                            style={"fontSize": "12px"}
                        )
                    ], className="mb-3"),
                    
                    # Relationship Type Checkboxes
                    html.Div([
                        html.Label(
                            "Relationship Types:",
                            style={
                                "fontSize": "11px",
                                "fontWeight": FONT_WEIGHT_SEMIBOLD,
                                "color": COLOR_GRAY_DARK,
                                "marginBottom": "8px",
                                "display": "block"
                            }
                        ),
                        dbc.Checklist(
                            id="relationship-type-filter",
                            options=[],  # Populated dynamically
                            value=[],   # All selected by default
                            inline=False,
                            className="graph-filter-checklist",
                            style={"fontSize": "12px"}
                        )
                    ], className="mb-3"),
                    
                    html.Div(
                        id="weight-based-filter-group",
                        children=[
                            # Weight Threshold Slider
                            html.Div([
                                html.Label(
                                    "Weight Threshold:",
                                    style={
                                        "fontSize": "11px",
                                        "fontWeight": FONT_WEIGHT_SEMIBOLD,
                                        "color": COLOR_GRAY_DARK,
                                        "marginBottom": "8px",
                                        "display": "block"
                                    }
                                ),
                                html.Div([
                                    dcc.Slider(
                                        id="weight-threshold-slider",
                                        min=0,
                                        max=100,
                                        step=1,
                                        value=0,
                                        marks={0: '0', 25: '25', 50: '50', 75: '75', 100: '100'},
                                        tooltip={"placement": "bottom", "always_visible": False}
                                    ),
                                    html.Small(
                                        id="weight-threshold-label",
                                        children="Show edges with weight ≥ 0",
                                        className="d-block mt-1",
                                        style={"fontSize": "10px", "color": "var(--color-text-secondary)"}
                                    )
                                ])
                            ], className="mb-3"),
                            
                            # Top-N Toggle
                            html.Div([
                                html.Label(
                                    "Edge Limit:",
                                    style={
                                        "fontSize": "11px",
                                        "fontWeight": FONT_WEIGHT_SEMIBOLD,
                                        "color": COLOR_GRAY_DARK,
                                        "marginBottom": "8px",
                                        "display": "block"
                                    }
                                ),
                                dbc.RadioItems(
                                    id="top-n-toggle",
                                    options=[
                                        {"label": "Show All", "value": "all"},
                                        {"label": "Top 50 Edges", "value": "top50"},
                                        {"label": "Top 100 Edges", "value": "top100"}
                                    ],
                                    value="all",
                                    inline=False,
                                    className="graph-filter-radio",
                                    style={"fontSize": "12px"}
                                )
                            ])
                        ]
                    ),

                    html.Div(
                        id="weight-filter-unavailable-note",
                        className="graph-filter-help-note",
                        style={"display": "none"},
                        children="Weight-based controls are available for weighted graphs only."
                    )
                ], className="graph-filter-card-body", style={"padding": "12px"})
            ], className="graph-filter-card", style={"border": f"1px solid {COLOR_GRAY_LIGHTER}", "borderRadius": "4px"})
            ]
        )
    ], className="mb-3")


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
                    
                    # Right sidebar: Filters + Details panel
                    dbc.Col([
                        create_filter_panel(),
                        html.Div(
                            id="graph-details-panel",
                            style=GRAPH_DETAILS_PANEL_STYLE,
                            children=[
                                html.Div([
                                    html.I(className="fas fa-info-circle fa-lg mb-2", style=GRAPH_DETAILS_PANEL_ICON_STYLE),
                                    html.P(
                                        "Execute a query to see the graph",
                                        className="mb-0",
                                        style={"fontSize": "12px", "color": "var(--color-text-secondary)"}
                                    )
                                ], className="text-center", style={"marginTop": "100px"})
                            ]
                        )
                    ], id="graph-details-col", width=4)
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
                    value="MATCH (n)-[r]->(m)\nRETURN n, r, m\nLIMIT 10",
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
    ], id="graph-query-section", style=GRAPH_QUERY_SECTION_CONTAINER_STYLE)


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
        
        # --- Phase 1.2.4: Relationship Filtering ---
        # Store for unfiltered graph elements (backup for reset)
        dcc.Store(id="unfiltered-elements-store", data=[]),

        # Store for live Cytoscape node positions (captured clientside)
        dcc.Store(id="node-positions-store", data={}),

        # Store for hovered node tooltip data (full label + cursor position)
        dcc.Store(id="node-hover-store", data=None),

        # Track previously available filter domains to detect newly introduced types
        # during expansion and keep "no active filtering" behavior intuitive.
        dcc.Store(id="node-type-available-store", data=[]),
        dcc.Store(id="relationship-type-available-store", data=[]),
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

        # Full-label tooltip shown on node hover (positioned clientside)
        html.Div(
            id="graph-node-hover-tooltip",
            style=GRAPH_NODE_HOVER_TOOLTIP_STYLE,
        ),
    ]


def get_layout():
    """Build complete graph page layout with Executive Dashboard aesthetic
    
    Returns:
        html.Div with full page layout
    """
    return html.Div([
        # Collaboration-mode info banner (hidden in normal mode)
        html.Div(id="collaboration-banner", children=[], style={"display": "none", "padding": "0 16px"}),

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
