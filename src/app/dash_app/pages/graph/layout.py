"""Graph page layout builder

This module constructs the complete UI layout for the graph visualization page,
broken down into logical sections for maintainability.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto

from .styles import CYTOSCAPE_STYLESHEET
from .components import create_expansion_modal, create_context_menu
from .utils.ui_components import create_performance_metrics

from app.dash_app.components.common import create_controls_bar

from app.dash_app.styles import (
    FONT_SANS,
    FONT_WEIGHT_SEMIBOLD,
    COLOR_BACKGROUND_WHITE,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_DARK,
    COLOR_GRAY_LIGHTER,
    COLOR_TEXT_SECONDARY,
    SPACING_XXSMALL,
    GRAPH_SECTION_TITLE_STYLE,
    GRAPH_QUERY_TEXTAREA_STYLE,
    GRAPH_HELPER_TEXT_STYLE,
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
    return create_controls_bar("graph")


def create_graph_container():
    """Create main graph visualization container with Cytoscape
    
    Returns:
        html.Div containing Cytoscape graph component
    """
    return html.Div(
        id="graph-cytoscape-container",
        style={"display": "none"},  # Hidden initially, then maintains consistent size after first query
        children=[
            cyto.Cytoscape(
                id="graph-cytoscape",
                elements=[],
                layout={'name': 'circle', 'animate': True},
                style=GRAPH_CYTOSCAPE_STYLE,
                stylesheet=CYTOSCAPE_STYLESHEET,
                userZoomingEnabled=True,
                userPanningEnabled=True,
                wheelSensitivity=0.3,
                minZoom=0.1,
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
            "minHeight": "calc(75vh)",
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


def _filter_card():
    """Returns the filter controls dbc.Card for the Filters tab collapse."""
    return dbc.Card([
        dbc.CardBody([
            html.Div([
                html.Div([
                    html.Small(
                        "Refining loaded graph",
                        id="filter-mode-label",
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
                    value=[],    # All selected by default
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
                    value=[],    # All selected by default
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
        ], className="graph-filter-card-body", style={"padding": "0 0 24px 0"})
    ], className="graph-filter-card", style={"border": "none", "backgroundColor": "transparent"})


def _console_card():
    """Returns the query console dbc.Card for the Console tab collapse."""
    return dbc.Card([
        dbc.CardBody([
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
                        color="primary",
                        size="sm",
                        style={"borderRadius": "2px"},
                        className="graph-execute-btn w-100"
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
        ], style={"padding": "16px"})
    ], style={"border": f"1px solid {COLOR_GRAY_LIGHTER}", "borderRadius": "2px", "backgroundColor": "var(--color-background-white)"})


def create_right_panel_tab_bar():
    """Create the sticky icon-only horizontal tab bar for the right panel workbench.

    Returns:
        html.Div containing 3 icon toggle buttons: Filters, Console, Catalog.
    """
    return html.Div(
        id="graph-right-panel-tab-bar",
        className="graph-right-panel-tab-bar",
        children=[
            html.Button(
                html.I(className="fas fa-sliders fa-fw"),
                id="right-tab-filters-btn",
                title="Filters",
                className="graph-right-panel-tab-icon",
                n_clicks=0,
            ),
            html.Button(
                html.I(className="fas fa-terminal fa-fw"),
                id="right-tab-console-btn",
                title="Console",
                className="graph-right-panel-tab-icon",
                n_clicks=0,
            ),
            html.Button(
                html.I(className="fas fa-book-open fa-fw"),
                id="right-tab-catalog-btn",
                title="Catalog",
                className="graph-right-panel-tab-icon",
                n_clicks=0,
            ),
        ]
    )


def create_catalog_tab_content():
    """Single-column catalog layout for the right panel Catalog tab.

    Returns:
        html.Div with namespace filter, search, query list, detail, and action buttons.
    """
    return html.Div([
        html.Label("Namespace", className="mb-1", style=GRAPH_HELPER_TEXT_STYLE),
        dbc.Select(
            id="catalog-namespace-filter",
            options=[{"label": "All namespaces", "value": "__all__"}],
            value="__all__",
            size="sm",
            className="mb-3",
        ),
        html.Label("Search", className="mb-1", style=GRAPH_HELPER_TEXT_STYLE),
        dbc.Input(
            id="catalog-search-input",
            placeholder="Find a query by name, tag, or description",
            type="text",
            size="sm",
            className="mb-3",
        ),
        html.Div(
            id="query-catalog-load-status",
            className="mb-2",
        ),
        html.Div(
            id="catalog-query-list",
            children=html.Div(
                "Loading catalog queries...",
                style={"fontSize": "12px", "color": COLOR_TEXT_SECONDARY}
            ),
            style={
                "maxHeight": "240px",
                "overflowY": "auto",
                "border": f"1px solid {COLOR_BORDER}",
                "borderRadius": "2px",
                "padding": "8px",
                "backgroundColor": COLOR_BACKGROUND_WHITE,
                "color": COLOR_CHARCOAL_MEDIUM,
            }
        ),
        html.Div(
            id="catalog-query-detail",
            children=html.Div(
                "Select a catalog query to inspect it here.",
                style={"fontSize": "12px", "color": COLOR_TEXT_SECONDARY}
            ),
            style={
                "border": f"1px solid {COLOR_BORDER}",
                "borderRadius": "2px",
                "padding": "12px",
                "backgroundColor": COLOR_BACKGROUND_WHITE,
                "color": COLOR_CHARCOAL_MEDIUM,
                "marginTop": "8px",
            },
        ),
        html.Div(
            id="catalog-parameter-inputs",
            className="mt-3",
        ),
        html.Div([
            html.Label("Display as", className="mb-1 mt-3", style=GRAPH_HELPER_TEXT_STYLE),
            dbc.RadioItems(
                id="catalog-query-view-toggle",
                options=[],
                value=None,
                inline=True,
                className="mb-2",
                input_class_name="me-1",
            ),
        ], id="catalog-view-toggle-container"),
        html.Div([
            dbc.Button(
                "Run",
                id="catalog-run-btn",
                color="primary",
                size="sm",
                className="me-2",
                disabled=True,
            ),
            dbc.Button(
                "Load into Console",
                id="catalog-load-console-btn",
                outline=True,
                color="secondary",
                size="sm",
                disabled=True,
            ),
        ], className="mt-3"),
    ], style={"padding": "8px 0"})


def create_right_panel_tabs():
    """Three accordion collapse panels for the right panel workbench.

    Returns:
        html.Div containing dbc.Collapse for Filters, Console, and Catalog tabs.
    """
    return html.Div([
        dbc.Collapse(
            id="right-tab-filters-collapse",
            is_open=False,
            children=[_filter_card()],
        ),
        dbc.Collapse(
            id="right-tab-console-collapse",
            is_open=False,
            children=[_console_card()],
        ),
        dbc.Collapse(
            id="right-tab-catalog-collapse",
            is_open=False,
            children=[create_catalog_tab_content()],
        ),
    ])


def create_results_section():
    """Create the results section (graph + details panel)
    
    Returns:
        html.Div containing the complete results section
    """
    return html.Div([
        dbc.Row([
            # Left col: controls bar + graph canvas (with loading indicator)
            dbc.Col([
                create_graph_controls(),
                html.Div(
                    id="graph-status-strip",
                    style={"display": "none", "marginBottom": "8px"}
                ),
                dcc.Loading(
                    id="graph-loading",
                    type="circle",
                    color=GRAPH_LOADING_COLOR,
                    children=[
                        create_graph_container(),
                        create_table_container(),
                        create_empty_state()
                    ]
                )
            ], id="graph-viz-col", width=8, style={"paddingRight": "24px"}),

            # Right col: workbench tab bar + tab panels + details panel
            dbc.Col([
                html.Div([
                    create_right_panel_tab_bar(),
                    create_right_panel_tabs(),
                    html.Div(
                        id="graph-details-panel",
                        style={
                            **GRAPH_DETAILS_PANEL_STYLE,
                            "border": "none",
                            "boxShadow": "none",
                            "padding": "0",
                            "backgroundColor": "transparent"
                        },
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
                ], style={"overflowY": "auto", "maxHeight": "calc(75vh + 40px)", "position": "relative"})
            ], id="graph-details-col", width=4, style={"borderLeft": f"1px solid {COLOR_GRAY_LIGHTER}", "paddingLeft": "24px"})
        ], className="g-0")
    ], className="mb-2")


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

        # Catalog workbench metadata/state
        dcc.Store(id="query-catalog-store", data=[]),
        dcc.Store(id="selected-catalog-query-store", data=None),
        dcc.Store(id="catalog-parameters-store", data={}),
        
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

        # Cypher auto-execute store: set by toggle_query_collapse when a
        # ?cypher= URL param is present; triggers execute_query automatically.
        dcc.Store(id="cypher-autoexec-store", storage_type="memory", data=None),
        
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

        # --- C3: Node Spotlight ---
        # Debounced spotlight query value (memory — resets on page nav)
        dcc.Store(id="spotlight-debounced-store", storage_type="memory", data=None),

        # Right panel workbench: tracks which tab is currently open ("filters", "console", "catalog", or None)
        dcc.Store(id="right-panel-active-tab", storage_type="memory", data="console"),
    ]


def create_hidden_elements():
    """Create hidden UI elements (triggers, etc.)
    
    Returns:
        List of hidden elements
    """
    return [
        # Performance metrics section — shown on load with zeroed defaults.
        html.Div(
            id="graph-performance-metrics",
            style={"display": "block"},
            children=create_performance_metrics(0, 0, 0, is_graph=True),
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
        # Results Section (graph visualization + details panel)
        create_results_section(),

        # Hidden elements (performance metrics, triggers)
        *create_hidden_elements(),
        
        # State stores (hidden)
        *create_stores(),
        
        # Context menu
        create_context_menu(),
        
        # Expansion modal
        create_expansion_modal(),
    ])
