"""Navigation Callbacks

Callbacks for graph navigation, keyboard shortcuts, and viewport controls.
"""

from dash import Input, Output, State, callback, clientside_callback
from dash.exceptions import PreventUpdate


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


# Clientside callback to capture current node positions for stable expansion
clientside_callback(
    """
    function(elements) {
        const elem = document.getElementById('graph-cytoscape');
        if (!elem || !elem._cyreg || !elem._cyreg.cy) {
            return window.dash_clientside.no_update;
        }

        const cy = elem._cyreg.cy;
        const positions = {};

        cy.nodes().forEach(function(node) {
            const pos = node.position();
            positions[node.id()] = { x: pos.x, y: pos.y };
        });

        return positions;
    }
    """,
    Output("node-positions-store", "data"),
    Input("graph-cytoscape", "elements"),
    prevent_initial_call=False
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


# Clientside callback to capture double-click events on nodes
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


# Clientside callback to capture right-click events on nodes
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


# Clientside callback for Ctrl+Enter to execute query
clientside_callback(
    """
    function(value) {
        // Attach listener to the textarea for Ctrl+Enter
        const textarea = document.getElementById('graph-query-input');
        if (textarea && !textarea._ctrlEnterListenerAttached) {
            textarea.addEventListener('keydown', function(e) {
                // Check for Ctrl+Enter or Cmd+Enter (Mac)
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault();
                    
                    // Programmatically click the execute button
                    const executeBtn = document.getElementById('graph-execute-btn');
                    if (executeBtn) {
                        executeBtn.click();
                    }
                }
            });
            
            textarea._ctrlEnterListenerAttached = true;
            console.log('[Graph Query] Ctrl+Enter listener attached to query input');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("graph-query-input", "className"),  # Dummy output
    Input("graph-query-input", "id"),
    prevent_initial_call=False
)


# Clientside callback for keyboard shortcuts
clientside_callback(
    """
    function(elements) {
        // Only attach listener once
        if (!window._keyboardListenerAttached) {
            document.addEventListener('keydown', function(e) {
                // Ignore if user is typing in an input field (except for specific shortcuts in textarea handled separately)
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
