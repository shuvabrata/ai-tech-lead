# Graph Page Refactoring Plan

**Status**: Planning 📋  
**Created**: March 2, 2026  
**Last Updated**: March 2, 2026  
**Parent Document**: `advanced-graph-navigation.md`  
**Context**: After completing Phase 1.1 (Node Expansion)

## Executive Summary

The `app/dash_app/pages/graph.py` file has grown to **2,262 lines** and will continue to grow significantly as we implement the remaining 7 phases of advanced graph navigation. This document outlines a refactoring strategy to:

1. **Reduce cognitive load** - Make it easier to find and modify code
2. **Improve testability** - Enable unit testing of utilities without Dash dependencies
3. **Prepare for future phases** - Allow new features to be added as new files, not more lines in one file
4. **Enable parallel development** - Multiple features can be worked on simultaneously
5. **Improve code review** - Smaller, focused files are easier to review

---

## Current State Analysis

### File Size Breakdown

**Total Lines**: 2,262

| Section | Line Range | Lines | Description |
|---------|-----------|-------|-------------|
| Imports & Constants | 1-143 | 143 | Cytoscape stylesheet, imports |
| Layout (`get_layout()`) | 144-481 | 337 | Complete UI layout definition |
| Utility Functions | 482-919 | 437 | Data transformation, UI components |
| Core Callbacks | 920-1375 | 455 | Query, display, layout controls |
| Phase 1.1c (Double-Click) | 1376-1422 | 46 | Clientside callback for double-click |
| Phase 1.1d (Context Menu) | 1423-2001 | 578 | Context menu logic and callbacks |
| Phase 1.1e (Keyboard) | 2002-2087 | 85 | Keyboard shortcuts |
| Phase 1.1b (Modal Expansion) | 2088-2262 | 174 | Expansion modal callbacks |

### Problems with Current Structure

1. **Difficult navigation** - Finding specific callbacks or components takes scrolling through 2000+ lines
2. **Merge conflicts** - Multiple features = multiple people editing same file
3. **Testing challenges** - Can't unit test utilities without Dash app context
4. **Future growth** - 7 more phases planned, could easily reach 5000+ lines
5. **Cognitive overload** - Too much context switching between UI, logic, and callbacks

---

## Proposed File Structure

```
app/dash_app/pages/graph/
├── __init__.py                      # Main entry point (exports get_layout)
├── styles.py                        # Cytoscape stylesheet constants (~140 lines)
├── layout.py                        # UI layout builder (~350 lines)
│
├── utils/
│   ├── __init__.py                  
│   ├── data_transform.py            # neo4j_to_cytoscape, error parsing (~120 lines)
│   ├── ui_components.py             # Alert/table/metrics creators (~200 lines)
│   └── formatters.py                # Property formatting (~50 lines)
│
├── callbacks/
│   ├── __init__.py                  # Registers all callbacks
│   ├── query.py                     # Query execution & validation (~200 lines)
│   ├── display.py                   # Property panel, layout control (~200 lines)
│   ├── expansion.py                 # All expansion logic (~500 lines)
│   ├── context_menu.py              # Context menu actions (~400 lines)
│   └── navigation.py                # Fit, keyboard shortcuts (~150 lines)
│
└── components/
    ├── __init__.py
    ├── modals.py                    # Expansion modal, future modals (~100 lines)
    └── menus.py                     # Context menu HTML (~80 lines)
```

**Total**: ~2,490 lines across **15 focused files** (vs. 2,262 in 1 file)

### File Size Targets

- **Maximum file size**: 500 lines (with exceptions for complex callbacks)
- **Target file size**: 100-300 lines (optimal for cognitive load)
- **Minimum file size**: 50 lines (avoid over-fragmentation)

---

## Detailed Refactoring Phases

### Phase R1: Extract Constants & Styles ✅

**Goal**: Separate visual configuration from logic  
**Risk**: Low  
**Estimated Time**: 30 minutes

#### Files to Create:

**`app/dash_app/pages/graph/styles.py`**

```python
"""Cytoscape style definitions for graph visualization

This module contains all visual styling for the graph visualization,
including node colors, sizes, edge styles, and selection states.
"""

CYTOSCAPE_STYLESHEET = [
    # Default node style
    {
        'selector': 'node',
        'style': {
            'label': 'data(label)',
            'background-color': '#B8B8B8',
            # ... (all existing styles from lines 21-143)
        }
    },
    # ... all other styles
]
```

#### Files to Modify:

**`app/dash_app/pages/graph.py`**
- Remove lines 21-143 (CYTOSCAPE_STYLESHEET definition)
- Add import: `from .styles import CYTOSCAPE_STYLESHEET`

#### Success Criteria:

- ✅ App runs without errors
- ✅ Graph visualization looks identical
- ✅ No import errors

---

### Phase R2: Extract Utility Functions ✅

**Goal**: Isolate pure functions for easier testing  
**Risk**: Low  
**Estimated Time**: 1-2 hours

#### Files to Create:

**`app/dash_app/pages/graph/utils/__init__.py`**

```python
"""Utility functions for graph visualization"""

from .data_transform import neo4j_to_cytoscape, parse_error_response
from .ui_components import (
    create_error_alert,
    create_table_display,
    create_graph_success_alert,
    create_performance_metrics,
    toggle_details_panel
)
from .formatters import format_property_value, build_property_items

__all__ = [
    'neo4j_to_cytoscape',
    'parse_error_response',
    'create_error_alert',
    'create_table_display',
    'create_graph_success_alert',
    'create_performance_metrics',
    'toggle_details_panel',
    'format_property_value',
    'build_property_items'
]
```

**`app/dash_app/pages/graph/utils/data_transform.py`**

```python
"""Data transformation utilities for graph visualization

Functions for converting between Neo4j format and Cytoscape format,
and parsing error responses from the backend API.
"""

def neo4j_to_cytoscape(graph_response):
    """Convert Neo4j graph response to Cytoscape elements
    
    Args:
        graph_response: Dict containing 'nodes' and 'relationships' from Neo4j
        
    Returns:
        List of Cytoscape elements (nodes and edges)
    """
    # ... existing implementation from line 490
    
def parse_error_response(error_data, status_code):
    """Parse error response from backend API
    
    Args:
        error_data: Error data from API response
        status_code: HTTP status code
        
    Returns:
        Tuple of (error_message, error_type, hint, doc_link)
    """
    # ... existing implementation from line 547
```

**`app/dash_app/pages/graph/utils/ui_components.py`**

```python
"""UI component builders for graph visualization

Functions for creating UI elements like alerts, tables, and metrics displays.
These are pure functions that return Dash components.
"""

import dash_bootstrap_components as dbc
from dash import html

def create_error_alert(message, alert_type='danger', hint=None, 
                       heading="Query Execution Failed", doc_link=None):
    """Create an error alert component
    
    Args:
        message: Error message to display
        alert_type: Bootstrap alert color ('danger', 'warning', 'info')
        hint: Optional hint text for user
        heading: Alert heading text
        doc_link: Optional documentation link
        
    Returns:
        dbc.Alert component
    """
    # ... existing implementation from line 647

def create_table_display(raw_results, result_count):
    """Create a table display for non-graph query results"""
    # ... existing implementation from line 704

def create_graph_success_alert(node_count, rel_count):
    """Create success alert for graph query results"""
    # ... existing implementation from line 745

def create_performance_metrics(node_count, rel_count, execution_time_ms, is_graph=True):
    """Create performance metrics panel"""
    # ... existing implementation from line 761

def toggle_details_panel(is_fullwidth):
    """Calculate details panel visibility based on fullwidth state"""
    # ... existing implementation from line 482
```

**`app/dash_app/pages/graph/utils/formatters.py`**

```python
"""Property formatting utilities

Functions for formatting node/edge property values for display.
"""

from datetime import datetime
from dash import html
import dash_bootstrap_components as dbc

def format_property_value(value):
    """Format a property value for display
    
    Args:
        value: Property value (any type)
        
    Returns:
        Formatted string or HTML component
    """
    # ... existing implementation from line 870

def build_property_items(properties):
    """Build a list of property display items
    
    Args:
        properties: Dict of properties
        
    Returns:
        List of dbc.ListGroupItem components
    """
    # ... existing implementation from line 899
```

#### Files to Modify:

**`app/dash_app/pages/graph.py`**
- Remove functions: `neo4j_to_cytoscape`, `_parse_error_response`, `_create_error_alert`, etc.
- Add imports: `from .utils import *`
- Update function names (remove underscore prefixes where needed)

#### Success Criteria:

- ✅ App runs without errors
- ✅ Query execution works
- ✅ Error handling works
- ✅ Can import utilities independently for testing

---

### Phase R3: Extract Components ✅

**Goal**: Modularize UI components for reusability  
**Risk**: Low  
**Estimated Time**: 1-2 hours

#### Files to Create:

**`app/dash_app/pages/graph/components/__init__.py`**

```python
"""UI components for graph visualization"""

from .modals import create_expansion_modal
from .menus import create_context_menu

__all__ = [
    'create_expansion_modal',
    'create_context_menu'
]
```

**`app/dash_app/pages/graph/components/modals.py`**

```python
"""Modal dialog components

Modal dialogs for graph interactions:
- Expansion modal (configure node expansion)
- Future: Filter modal, search modal, etc.
"""

import dash_bootstrap_components as dbc
from dash import html, dcc

def create_expansion_modal():
    """Create the node expansion configuration modal
    
    Returns:
        dbc.Modal component for node expansion
    """
    return dbc.Modal([
        dbc.ModalHeader("Expand Node"),
        dbc.ModalBody([
            html.Div([
                html.Label("Direction:", className="fw-bold mb-2"),
                dcc.Dropdown(
                    id="expansion-direction-selector",
                    options=[
                        {"label": "Both (Incoming + Outgoing)", "value": "both"},
                        {"label": "Outgoing Only", "value": "outgoing"},
                        {"label": "Incoming Only", "value": "incoming"}
                    ],
                    value="both",
                    clearable=False,
                    className="mb-3"
                ),
                html.Small(
                    "Which relationships to follow",
                    className="text-muted",
                    style={"fontSize": "11px"}
                )
            ]),
            html.Div([
                html.Label("Limit:", className="fw-bold mb-2"),
                dbc.Input(
                    id="expansion-limit-input",
                    type="number",
                    min=1,
                    max=500,
                    step=1,
                    value=50,
                    className="mb-2"
                ),
                html.Small(
                    "Will load up to this many neighbors (1-500)",
                    className="text-muted",
                    style={"fontSize": "11px"}
                )
            ]),
            html.Div([
                dbc.Checkbox(
                    id="expansion-auto-fit-checkbox",
                    label="Auto-fit graph after expansion",
                    value=True,
                    className="mt-3"
                ),
                html.Small(
                    "Automatically zoom to show all nodes",
                    className="text-muted d-block",
                    style={"fontSize": "11px", "marginLeft": "24px"}
                )
            ]),
        ]),
        dbc.ModalFooter([
            dbc.Button(
                "Cancel",
                id="expansion-modal-cancel",
                color="secondary",
                size="sm",
                className="me-2"
            ),
            dbc.Button(
                "Expand",
                id="expansion-modal-expand",
                color="primary",
                size="sm"
            )
        ])
    ], id="expansion-modal", is_open=False, size="sm")
```

**`app/dash_app/pages/graph/components/menus.py`**

```python
"""Context menu components

Right-click context menus for graph interactions.
"""

from dash import html

def create_context_menu():
    """Create the right-click context menu for nodes
    
    Returns:
        html.Div containing context menu structure
    """
    return html.Div([
        html.Div("Expand Node...", 
                 id="ctx-menu-expand", 
                 className="context-menu-item",
                 style={
                     "padding": "8px 12px",
                     "cursor": "pointer",
                     "fontSize": "13px",
                     "borderBottom": "1px solid #e0e0e0"
                 }),
        html.Div("Quick Expand Incoming", 
                 id="ctx-menu-expand-incoming", 
                 className="context-menu-item",
                 style={
                     "padding": "8px 12px",
                     "cursor": "pointer",
                     "fontSize": "13px"
                 }),
        html.Div("Quick Expand Outgoing", 
                 id="ctx-menu-expand-outgoing", 
                 className="context-menu-item",
                 style={
                     "padding": "8px 12px",
                     "cursor": "pointer",
                     "fontSize": "13px",
                     "borderBottom": "1px solid #e0e0e0"
                 }),
        html.Div("Copy Node ID", 
                 id="ctx-menu-copy-id", 
                 className="context-menu-item",
                 style={
                     "padding": "8px 12px",
                     "cursor": "pointer",
                     "fontSize": "13px"
                 }),
        html.Div("Remove from View", 
                 id="ctx-menu-remove", 
                 className="context-menu-item",
                 style={
                     "padding": "8px 12px",
                     "cursor": "pointer",
                     "fontSize": "13px",
                     "color": "#dc3545"
                 })
    ], id="context-menu", className="context-menu", style={
        "display": "none",
        "position": "absolute",
        "backgroundColor": "white",
        "border": "1px solid #ccc",
        "borderRadius": "4px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.15)",
        "zIndex": 10000,
        "minWidth": "180px"
    })
```

#### Files to Modify:

**`app/dash_app/pages/graph.py`**
- Extract modal definition from `get_layout()`
- Extract context menu definition from `get_layout()`
- Add imports: `from .components import create_expansion_modal, create_context_menu`
- Call component functions in `get_layout()`

#### Success Criteria:

- ✅ App runs without errors
- ✅ Expansion modal works
- ✅ Context menu works
- ✅ UI looks identical

---

### Phase R4: Refactor Layout Builder ✅

**Goal**: Break down massive `get_layout()` function  
**Risk**: Medium  
**Estimated Time**: 2-3 hours

#### Files to Create:

**`app/dash_app/pages/graph/layout.py`**

```python
"""Graph page layout builder

This module constructs the complete UI layout for the graph visualization page,
broken down into logical sections for maintainability.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto

from .styles import CYTOSCAPE_STYLESHEET
from .components import create_expansion_modal, create_context_menu

def _create_query_controls():
    """Create query input and execution controls
    
    Returns:
        dbc.Card containing query textarea and execute button
    """
    return dbc.Card([
        dbc.CardBody([
            html.Label("Cypher Query:", className="fw-bold mb-2"),
            dcc.Textarea(
                id="graph-query-input",
                placeholder="Enter your Cypher query here...\nExample: MATCH (n) RETURN n LIMIT 10",
                style={
                    "width": "100%",
                    "height": "120px",
                    "fontFamily": "monospace",
                    "fontSize": "13px"
                },
                className="mb-2"
            ),
            html.Div(id="query-validation-message", className="mb-2"),
            dbc.Button(
                "Execute Query",
                id="graph-execute-btn",
                color="primary",
                size="sm"
            )
        ])
    ], className="mb-3")

def _create_layout_controls():
    """Create layout selector and graph control buttons
    
    Returns:
        html.Div containing layout controls
    """
    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Label("Layout:", className="me-2 mb-0"),
                dcc.Dropdown(
                    id="graph-layout-selector",
                    options=[
                        {"label": "Cola (Force-Directed)", "value": "cola"},
                        {"label": "Cose (Compound Spring)", "value": "cose"},
                        {"label": "Circle", "value": "circle"},
                        {"label": "Grid", "value": "grid"},
                        {"label": "Breadthfirst", "value": "breadthfirst"},
                        {"label": "Concentric", "value": "concentric"}
                    ],
                    value="cola",
                    clearable=False,
                    style={"width": "200px", "display": "inline-block"}
                )
            ], width="auto"),
            dbc.Col([
                dbc.Button(
                    [html.I(className="fas fa-compress-arrows-alt me-1"), "Fit"],
                    id="graph-fit-btn",
                    color="secondary",
                    size="sm",
                    className="me-2"
                ),
                dbc.Button(
                    [html.I(className="fas fa-redo me-1"), "Reset"],
                    id="graph-reset-btn",
                    color="secondary",
                    size="sm",
                    className="me-2"
                ),
                dbc.Button(
                    [html.I(className="fas fa-expand me-1")],
                    id="graph-fullwidth-btn",
                    color="secondary",
                    size="sm",
                    title="Toggle fullwidth"
                )
            ], width="auto")
        ], className="mb-3 align-items-center")
    ])

def _create_graph_container():
    """Create main graph visualization container
    
    Returns:
        dbc.Col containing Cytoscape graph
    """
    return dbc.Col([
        html.Div([
            html.Div(id="graph-results-container", style={"display": "none"}),
            html.Div(
                cyto.Cytoscape(
                    id='graph-cytoscape',
                    elements=[],
                    stylesheet=CYTOSCAPE_STYLESHEET,
                    layout={'name': 'cola'},
                    style={'width': '100%', 'height': '600px'},
                    boxSelectionEnabled=True
                ),
                id="graph-cytoscape-container",
                style={"display": "none"}
            ),
            html.Div(id="graph-table-container", style={"display": "none"})
        ]),
        html.Div(id="graph-performance-metrics", className="mt-2", style={"display": "none"})
    ], id="graph-viz-col", width=12)

def _create_details_panel():
    """Create details panel for selected nodes/edges
    
    Returns:
        dbc.Col containing details panel
    """
    return dbc.Col([
        dbc.Card([
            dbc.CardHeader(html.H5("Details", className="mb-0")),
            dbc.CardBody(
                html.Div(id="graph-details-panel", children=[
                    html.P("Select a node or edge to view details.", 
                           className="text-muted mb-0")
                ])
            )
        ])
    ], id="graph-details-col", width=3, style={"display": "block"})

def _create_stores():
    """Create all dcc.Store components for state management
    
    Returns:
        List of dcc.Store components
    """
    return [
        dcc.Store(id="graph-data-store", data=None),
        dcc.Store(id="graph-fullwidth-state", data=False),
        dcc.Store(id="loaded-node-ids", data=[]),
        dcc.Store(id="expanded-nodes", data={}),
        dcc.Store(id="selected-node-for-expansion", data=None),
        dcc.Store(id="expansion-debounce-store", data={}),
        dcc.Store(id="doubleclicked-node-store", data=None),
        dcc.Store(id="rightclicked-node-store", data=None),
        dcc.Store(id="keyboard-shortcut-store", data=None)
    ]

def _create_hidden_elements():
    """Create hidden UI elements (triggers, etc.)
    
    Returns:
        List of hidden elements
    """
    return [
        html.Div(id="graph-fit-trigger", style={"display": "none"})
    ]

def get_layout():
    """Build complete graph page layout
    
    Returns:
        dbc.Container with full page layout
    """
    return dbc.Container([
        # Page header
        html.H2("Graph Visualization", className="mb-3"),
        
        # Query controls
        _create_query_controls(),
        
        # Layout controls
        _create_layout_controls(),
        
        # Main content: graph + details panel
        dbc.Row([
            _create_graph_container(),
            _create_details_panel()
        ]),
        
        # Modals
        create_expansion_modal(),
        
        # Context menus
        create_context_menu(),
        
        # Hidden stores (state management)
        html.Div(_create_stores(), style={"display": "none"}),
        
        # Hidden elements
        html.Div(_create_hidden_elements(), style={"display": "none"})
        
    ], fluid=True)
```

#### Files to Modify:

**`app/dash_app/pages/graph.py`**
- Remove `get_layout()` function (lines 144-481)
- Add import: `from .layout import get_layout`

#### Success Criteria:

- ✅ App runs without errors
- ✅ All UI elements render correctly
- ✅ Layout looks identical to before

---

### Phase R5: Organize Callbacks by Feature ✅

**Goal**: Split 1500+ lines of callbacks into focused modules  
**Risk**: High (most complex phase)  
**Estimated Time**: 1-2 days

#### Files to Create:

**`app/dash_app/pages/graph/callbacks/__init__.py`**

```python
"""Callback registration for graph visualization

This module coordinates registration of all callbacks for the graph page.
Callbacks are organized by feature into separate modules.
"""

from . import query
from . import display
from . import expansion
from . import context_menu
from . import navigation

def register_all_callbacks():
    """Register all graph page callbacks
    
    This function must be called once when the app starts.
    It registers callbacks from all feature modules.
    """
    query.register_callbacks()
    display.register_callbacks()
    expansion.register_callbacks()
    context_menu.register_callbacks()
    navigation.register_callbacks()
```

**`app/dash_app/pages/graph/callbacks/query.py`**

```python
"""Query execution and validation callbacks

Handles:
- Real-time query validation
- Cypher query execution
- Result display (graph and tabular)
"""

from dash import callback, Input, Output, State
from dash.exceptions import PreventUpdate
import requests

from app.settings import settings
from ..utils import (
    neo4j_to_cytoscape,
    parse_error_response,
    create_error_alert,
    create_table_display,
    create_graph_success_alert,
    create_performance_metrics
)

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT


def register_callbacks():
    """Register query-related callbacks"""
    
    @callback(
        Output("query-validation-message", "children"),
        Input("graph-query-input", "value")
    )
    def validate_query(query_text):
        """Validate Cypher query syntax in real-time"""
        # ... existing implementation from line 984
    
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
        # ... existing implementation from line 1040
```

**`app/dash_app/pages/graph/callbacks/display.py`**

```python
"""Display and UI control callbacks

Handles:
- Property details panel
- Layout switching
- Fullwidth toggle
- Graph fit/reset
"""

from dash import callback, clientside_callback, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import html

from ..utils import format_property_value, build_property_items, toggle_details_panel


def register_callbacks():
    """Register display and UI control callbacks"""
    
    # Clientside callback for fit button
    clientside_callback(
        """
        function(n_clicks) {
            if (n_clicks) {
                const elem = document.getElementById('graph-cytoscape');
                if (elem && elem._cyreg && elem._cyreg.cy) {
                    elem._cyreg.cy.fit(null, 30);
                }
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("graph-fit-btn", "className"),
        Input("graph-fit-btn", "n_clicks"),
        prevent_initial_call=True
    )
    
    # Clientside callback for programmatic fit trigger
    clientside_callback(
        """
        function(trigger_value) {
            if (trigger_value) {
                const elem = document.getElementById('graph-cytoscape');
                if (elem && elem._cyreg && elem._cyreg.cy) {
                    elem._cyreg.cy.fit(null, 30);
                }
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("graph-fit-trigger", "className"),
        Input("graph-fit-trigger", "children"),
        prevent_initial_call=True
    )
    
    @callback(
        [Output("graph-fullwidth-state", "data"),
         Output("graph-viz-col", "width"),
         Output("graph-details-col", "style")],
        Input("graph-fullwidth-btn", "n_clicks"),
        State("graph-fullwidth-state", "data"),
        prevent_initial_call=True
    )
    def toggle_fullwidth(_n_clicks, is_fullwidth):
        """Toggle fullwidth visualization mode"""
        # ... existing implementation from line 972
    
    @callback(
        Output("graph-details-panel", "children"),
        [Input("graph-cytoscape", "selectedNodeData"),
         Input("graph-cytoscape", "selectedEdgeData")]
    )
    def display_properties(selected_nodes, selected_edges):
        """Display properties of selected node or edge"""
        # ... existing implementation from line 1197
    
    @callback(
        Output("graph-cytoscape", "layout"),
        [Input("graph-layout-selector", "value"),
         Input("graph-reset-btn", "n_clicks")],
        [State("graph-cytoscape", "layout")],
        prevent_initial_call=True
    )
    def update_layout(layout_name, reset_clicks, current_layout):
        """Update graph layout algorithm"""
        # ... existing implementation from line 1341
```

**`app/dash_app/pages/graph/callbacks/expansion.py`**

```python
"""Node expansion callbacks

Handles:
- Double-click expansion (clientside listener + Python handler)
- Modal-based expansion (with direction/limit controls)
- Expansion API calls and result merging
"""

from dash import callback, clientside_callback, Input, Output, State, callback_context
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import html
import requests
from datetime import datetime

from app.settings import settings
from ..utils import create_error_alert

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT


def register_callbacks():
    """Register node expansion callbacks"""
    
    # Clientside: Capture double-click events
    clientside_callback(
        """
        function(elements) {
            const elem = document.getElementById('graph-cytoscape');
            if (!elem || !elem._cyreg || !elem._cyreg.cy) {
                return window.dash_clientside.no_update;
            }
            
            const cy = elem._cyreg.cy;
            
            if (!cy._dbltapListenerAttached) {
                cy.on('dbltap', 'node', function(evt) {
                    const node = evt.target;
                    const nodeId = node.id();
                    
                    const data = {
                        node_id: nodeId,
                        timestamp: Date.now()
                    };
                    
                    if (window.dash_clientside && window.dash_clientside.set_props) {
                        window.dash_clientside.set_props('doubleclicked-node-store', { data: data });
                    }
                });
                
                cy._dbltapListenerAttached = true;
                console.log('[Phase 1.1c] Double-click event listener attached');
            }
            
            return window.dash_clientside.no_update;
        }
        """,
        Output("doubleclicked-node-store", "data"),
        Input("graph-cytoscape", "elements"),
        prevent_initial_call=False
    )
    
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
        """Handle double-click quick expansion"""
        # ... existing implementation from line 1508
    
    @callback(
        [Output("expansion-modal", "is_open", allow_duplicate=True),
         Output("selected-node-for-expansion", "data")],
        Input("expand-node-btn", "n_clicks"),
        [State("graph-cytoscape", "selectedNodeData")],
        prevent_initial_call=True
    )
    def open_expansion_modal(n_clicks, selected_nodes):
        """Open expansion modal for selected node"""
        # ... existing implementation from line 2101
    
    @callback(
        Output("expansion-modal", "is_open", allow_duplicate=True),
        Input("expansion-modal-cancel", "n_clicks"),
        prevent_initial_call=True
    )
    def close_expansion_modal(n_clicks):
        """Close expansion modal"""
        # ... existing implementation from line 2116
    
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
    def execute_node_expansion(n_clicks, node_id, direction, limit, auto_fit,
                               current_elements, loaded_node_ids, expanded_nodes,
                               current_layout, current_fit_count):
        """Execute modal-based node expansion"""
        # ... existing implementation from line 2145
```

**`app/dash_app/pages/graph/callbacks/context_menu.py`**

```python
"""Context menu callbacks

Handles:
- Right-click event capture (clientside)
- Context menu display and positioning
- Menu actions (expand, copy, remove)
"""

from dash import callback, clientside_callback, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import html
import requests
from datetime import datetime

from app.settings import settings

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT


def register_callbacks():
    """Register context menu callbacks"""
    
    # Clientside: Capture right-click events
    clientside_callback(
        """
        function(elements) {
            const elem = document.getElementById('graph-cytoscape');
            if (!elem || !elem._cyreg || !elem._cyreg.cy) {
                return window.dash_clientside.no_update;
            }
            
            const cy = elem._cyreg.cy;
            
            if (!cy._cxttapListenerAttached) {
                cy.on('cxttap', 'node', function(evt) {
                    evt.originalEvent.preventDefault();
                    
                    const node = evt.target;
                    const nodeId = node.id();
                    const x = evt.originalEvent.clientX;
                    const y = evt.originalEvent.clientY;
                    
                    const data = {
                        node_id: nodeId,
                        x: x,
                        y: y,
                        timestamp: Date.now()
                    };
                    
                    if (window.dash_clientside && window.dash_clientside.set_props) {
                        window.dash_clientside.set_props('rightclicked-node-store', { data: data });
                    }
                });
                
                const container = elem.parentElement;
                if (container) {
                    container.addEventListener('contextmenu', function(e) {
                        if (e.target === elem || elem.contains(e.target)) {
                            e.preventDefault();
                        }
                    });
                }
                
                cy._cxttapListenerAttached = true;
                console.log('[Phase 1.1d] Right-click event listener attached');
            }
            
            return window.dash_clientside.no_update;
        }
        """,
        Output("rightclicked-node-store", "data"),
        Input("graph-cytoscape", "elements"),
        prevent_initial_call=False
    )
    
    @callback(
        Output("context-menu", "style"),
        Input("rightclicked-node-store", "data"),
        State("context-menu", "style"),
        prevent_initial_call=True
    )
    def show_context_menu(rightclick_data, current_menu_style):
        """Show context menu at click position"""
        # ... existing implementation from line 1661
    
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
        # ... existing implementation from line 1688
    
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
        """Quick expansion from context menu"""
        # ... existing implementation from line 1721
    
    # Clientside: Copy node ID to clipboard
    clientside_callback(
        """
        function(n_clicks, rightclick_data) {
            if (n_clicks && rightclick_data && rightclick_data.node_id) {
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
    
    @callback(
        Output("context-menu", "style", allow_duplicate=True),
        Input("ctx-menu-copy-id", "n_clicks"),
        State("context-menu", "style"),
        prevent_initial_call=True
    )
    def hide_menu_after_copy(n_clicks, menu_style):
        """Hide context menu after copy action"""
        # ... existing implementation from line 1898
    
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
        # ... existing implementation from line 1919
    
    # Clientside: Hide menu on outside click and add hover effects
    clientside_callback(
        """
        function(n_intervals) {
            if (!window._contextMenuClickListenerAdded) {
                document.addEventListener('click', function(e) {
                    const menu = document.getElementById('context-menu');
                    if (menu && menu.style.display === 'block') {
                        if (!menu.contains(e.target)) {
                            menu.style.display = 'none';
                        }
                    }
                });
                
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
                console.log('[Phase 1.1d] Context menu listeners attached');
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("context-menu", "className"),
        Input("graph-cytoscape", "elements"),
        prevent_initial_call=False
    )
```

**`app/dash_app/pages/graph/callbacks/navigation.py`**

```python
"""Navigation and keyboard shortcut callbacks

Handles:
- Keyboard shortcuts (E = expand, F = fit)
- Graph fit/zoom controls
"""

from dash import callback, clientside_callback, Input, Output, State
from dash.exceptions import PreventUpdate


def register_callbacks():
    """Register navigation and keyboard shortcut callbacks"""
    
    # Clientside: Capture keyboard shortcuts
    clientside_callback(
        """
        function(elements) {
            if (!window._keyboardListenerAttached) {
                document.addEventListener('keydown', function(e) {
                    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                        return;
                    }
                    
                    const key = e.key.toLowerCase();
                    const timestamp = Date.now();
                    
                    if (key === 'e') {
                        e.preventDefault();
                        if (window.dash_clientside && window.dash_clientside.set_props) {
                            window.dash_clientside.set_props('keyboard-shortcut-store', {
                                data: { key: 'e', action: 'expand', timestamp: timestamp }
                            });
                        }
                    }
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
                console.log('[Phase 1.1e] Keyboard shortcuts attached (E, F)');
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("keyboard-shortcut-store", "data"),
        Input("graph-cytoscape", "elements"),
        prevent_initial_call=False
    )
    
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
        """Handle keyboard shortcuts"""
        # ... existing implementation from line 2062
```

#### Files to Modify:

**`app/dash_app/pages/graph.py`**
- Remove ALL callback definitions
- This file becomes essentially empty after R5

**`app/dash_app/pages/graph/__init__.py`**
- Add callback registration: `register_all_callbacks()`

#### Migration Strategy for R5:

Because this is the highest-risk phase, do it incrementally:

1. **R5a**: Extract `query.py` callbacks first (validate independently)
2. **R5b**: Extract `display.py` callbacks (test UI controls)
3. **R5c**: Extract `expansion.py` callbacks (test expansion features)
4. **R5d**: Extract `context_menu.py` callbacks (test right-click)
5. **R5e**: Extract `navigation.py` callbacks (test keyboard shortcuts)

Each sub-phase should be tested independently before proceeding.

#### Success Criteria:

- ✅ App runs without errors
- ✅ Query execution works
- ✅ All expansion methods work (modal, double-click, right-click)
- ✅ Context menu works
- ✅ Keyboard shortcuts work
- ✅ Layout controls work
- ✅ Details panel works

---

### Phase R6: Final Integration & Testing ✅

**Goal**: Clean up, test, and document the refactored structure  
**Risk**: Low  
**Estimated Time**: 2-4 hours

#### Tasks:

1. **Delete Original File**
   - Remove `app/dash_app/pages/graph.py` entirely
   - Ensure all functionality is in new structure

2. **Update Main Entry Point**

**`app/dash_app/pages/graph/__init__.py`**

```python
"""Graph Visualization Page

This module provides comprehensive graph visualization capabilities for exploring
Neo4j data through Cypher queries and interactive navigation.

Features:
- Cypher query execution
- Interactive graph visualization
- Node expansion (double-click, modal, right-click)
- Context menus
- Keyboard shortcuts (E = expand, F = fit)
- Layout algorithms
- Property inspection

Structure:
- layout.py: UI layout builder
- styles.py: Visual styling
- components/: Reusable UI components
- utils/: Pure utility functions
- callbacks/: Feature-organized callbacks
"""

from .layout import get_layout
from .callbacks import register_all_callbacks

# Auto-register all callbacks when module is imported
register_all_callbacks()

__all__ = ['get_layout']
```

3. **Update Tests**
   - Update test imports
   - Add unit tests for utilities
   - Add integration tests for callbacks

4. **Documentation**
   - Update README with new structure
   - Add docstrings to all new modules
   - Document callback dependencies

5. **Validation**
   - Run full test suite
   - Manual testing of all features
   - Performance comparison

#### Success Criteria:

- ✅ All tests pass
- ✅ No regressions in functionality
- ✅ Code coverage maintained or improved
- ✅ Documentation up to date
- ✅ Performance unchanged or improved

---

## Benefits Analysis

### Before Refactoring

**Problems:**
- 😵 2,262 lines in one file
- 🐌 Slow to navigate and find code
- 🔥 Merge conflicts likely with multiple features
- 🧪 Hard to test (everything coupled to Dash)
- 📈 Will grow to 5000+ lines with 7 more phases
- 🤯 Cognitive overload

### After Refactoring

**Benefits:**
- ✅ **Reduced cognitive load**: Max 500 lines per file, average 200
- ✅ **Easier navigation**: Find code by feature, not by scrolling
- ✅ **Better testability**: Pure functions can be unit tested
- ✅ **Easier collaboration**: Work on different features in different files
- ✅ **Scalable**: New phases add files, not lines
- ✅ **Better code review**: Review one feature at a time
- ✅ **Clearer dependencies**: Explicit imports show relationships

### Metrics Comparison

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Files | 1 | 15 | +1400% |
| Max file size | 2,262 lines | ~500 lines | -78% |
| Avg file size | 2,262 lines | ~166 lines | -93% |
| Testable utils | 0 | 9 functions | ∞ |
| Callback modules | 1 | 5 | +400% |
| Merge conflicts | High risk | Low risk | ✅ |

---

## Migration Timeline

### Incremental Approach (RECOMMENDED)

**Week 1**: Phases R1-R2 (2-3 hours)
- Extract constants and utilities
- Low risk, immediate benefit
- Test: Import utilities independently

**Week 2**: Phases R3-R4 (3-5 hours)
- Extract components and refactor layout
- Medium risk, structural improvement
- Test: UI renders correctly

**Week 3**: Phase R5 (6-10 hours)
- Extract callbacks (do incrementally: R5a → R5b → R5c → R5d → R5e)
- High risk, highest benefit
- Test: Each feature independently

**Week 4**: Phase R6 (2-4 hours)
- Final integration, testing, documentation
- Low risk, cleanup
- Test: Full regression suite

**Total Time**: 13-22 hours spread over 4 weeks

### Big Bang Approach (NOT RECOMMENDED)

Do all phases in 2-3 days, test comprehensively, merge.

**Risk**: High - many changes at once, hard to debug if something breaks
**When to use**: Only if you have comprehensive automated tests

---

## Testing Strategy

### Unit Tests (New)

Test pure utility functions without Dash:

```python
# tests/unit/graph/test_formatters.py
from app.dash_app.pages.graph.utils.formatters import format_property_value

def test_format_datetime():
    value = "2024-03-02T10:30:00Z"
    result = format_property_value(value)
    assert "2024-03-02" in str(result)

def test_format_none():
    result = format_property_value(None)
    assert "N/A" in str(result)
```

### Integration Tests (Updated)

Update existing tests with new imports:

```python
# tests/integration/test_graph_page.py
from app.dash_app.pages.graph import get_layout

def test_layout_renders():
    layout = get_layout()
    assert layout is not None
```

### Manual Testing Checklist

After each phase:
- [ ] Query execution works
- [ ] Graph renders correctly
- [ ] Node selection works
- [ ] Double-click expansion works
- [ ] Right-click menu works
- [ ] Keyboard shortcuts work (E, F)
- [ ] Modal expansion works
- [ ] Layout switching works
- [ ] Fullwidth toggle works
- [ ] Details panel displays properties

---

## Rollback Plan

If refactoring causes issues:

### Quick Rollback
```bash
# Revert to before refactoring started
git revert <refactoring-commit-hash>
```

### Incremental Rollback
If using incremental approach, can rollback individual phases:
```bash
# Rollback just Phase R5 (callbacks)
git revert <R5-commit-hash>
# Keep R1-R4 changes (styles, utils, components, layout)
```

### Backup Strategy
Before starting refactoring:
```bash
# Create backup branch
git branch backup-before-refactoring
```

---

## Future Phase Additions

### Phase 1.2: Enhanced Relationship Visibility

**New Files**:
- `app/dash_app/pages/graph/callbacks/relationships.py` (~150 lines)

**Modified Files**:
- `app/dash_app/pages/graph/styles.py` (add edge styles)
- `app/dash_app/pages/graph/layout.py` (add relationship filter controls)
- `app/dash_app/pages/graph/callbacks/__init__.py` (register new callbacks)

### Phase 1.4: Breadcrumb Navigation

**New Files**:
- `app/dash_app/pages/graph/components/breadcrumb.py` (~100 lines)
- `app/dash_app/pages/graph/callbacks/history.py` (~200 lines)

**Modified Files**:
- `app/dash_app/pages/graph/layout.py` (add breadcrumb to UI)
- `app/dash_app/pages/graph/callbacks/__init__.py` (register history callbacks)

### Phase 2: Filtering & Search

**New Files**:
- `app/dash_app/pages/graph/components/filter_panel.py` (~150 lines)
- `app/dash_app/pages/graph/components/search_bar.py` (~100 lines)
- `app/dash_app/pages/graph/callbacks/filtering.py` (~300 lines)
- `app/dash_app/pages/graph/callbacks/search.py` (~200 lines)

**Modified Files**:
- `app/dash_app/pages/graph/layout.py` (add filter panel and search bar)
- `app/dash_app/pages/graph/callbacks/__init__.py` (register new callbacks)

**Pattern**: Each new phase adds 2-4 new files, modifies 2-3 existing files. No monolithic file growth.

---

## Decision Log

### Decision 1: Module Structure
**Question**: Package (`graph/`) vs flat files (`graph_*.py`)?  
**Decision**: Package structure  
**Rationale**: Better organization, clearer imports, easier to add files

### Decision 2: Callback Organization
**Question**: By layer (all clientside vs Python) or by feature?  
**Decision**: By feature  
**Rationale**: Easier to understand complete feature behavior, reduce cross-file navigation

### Decision 3: Utility Organization
**Question**: Single `utils.py` or multiple files?  
**Decision**: Multiple files (`data_transform.py`, `ui_components.py`, `formatters.py`)  
**Rationale**: Clearer responsibilities, easier to find functions

### Decision 4: Component Pattern
**Question**: Components in layout.py or separate?  
**Decision**: Separate `components/` directory  
**Rationale**: Reusability, future phases will add more components (filter panel, search bar)

### Decision 5: Migration Strategy
**Question**: Big bang or incremental?  
**Decision**: Incremental (6 phases over 4 weeks)  
**Rationale**: Lower risk, easier to test, can rollback individual phases

---

## Success Metrics

### Code Quality
- ✅ Max file size reduced from 2,262 to ~500 lines
- ✅ Average file size ~166 lines
- ✅ All functions have docstrings
- ✅ Type hints on all functions

### Testability
- ✅ 9 pure utility functions can be unit tested
- ✅ Test coverage maintained or improved
- ✅ Integration tests pass

### Developer Experience
- ✅ Find code by feature name (not by scrolling)
- ✅ Edit one feature without touching others
- ✅ Code review focused on single feature
- ✅ Merge conflicts rare

### Performance
- ✅ No regression in page load time
- ✅ No regression in callback execution time
- ✅ Import time acceptable (<2s)

---

## Next Steps

1. **Review this plan** - Get approval from stakeholders
2. **Create refactoring branch** - `git checkout -b refactor/graph-page-modularization`
3. **Start Phase R1** - Extract styles (low risk, quick win)
4. **Incremental execution** - Complete one phase, test, commit, move to next
5. **Final review** - Comprehensive testing before merging to main

---

**Status**: Ready to begin 🚀  
**Recommendation**: Start with Phase R1 (styles extraction) immediately
