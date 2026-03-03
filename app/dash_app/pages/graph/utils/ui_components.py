"""UI component builders for graph visualization

Functions for creating UI elements like alerts, tables, and metrics displays.
These are pure functions that return Dash components.
"""

import dash_bootstrap_components as dbc
from dash import html

from ..styles import get_node_type_styles


def toggle_details_panel(is_fullwidth):
    """Helper function to calculate column widths based on panel state
    
    Args:
        is_fullwidth (bool): Whether the graph is in fullwidth mode
        
    Returns:
        tuple: (graph_width, panel_style_dict)
    """
    if is_fullwidth:
        return 12, {"display": "none"}  # Full width graph, hide panel
    else:
        return 8, {}  # Normal width, show panel


def create_error_alert(message, alert_type='danger', hint=None, heading="Query Execution Failed", doc_link=None):
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


def create_table_display(raw_results, result_count):
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


def create_graph_success_alert(node_count, rel_count):
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


def create_performance_metrics(node_count, rel_count, execution_time_ms, is_graph=True):
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


def create_expansion_success_alert(node_count, rel_count, has_more=False):
    """Create a success alert for node expansion
    
    Args:
        node_count (int): Number of nodes loaded
        rel_count (int): Number of relationships loaded
        has_more (bool): Whether more nodes are available beyond the limit
    
    Returns:
        dbc.Alert: Success alert component
    """
    message_parts = [
        html.I(className="fas fa-check-circle me-2"),
        f"Expansion complete! Loaded {node_count} new nodes, {rel_count} new relationships"
    ]
    if has_more:
        message_parts.extend([
            html.Span(" "),
            html.I(className="fas fa-exclamation-triangle me-1", style={"color": "#ffc107"}),
            html.Span("More available", style={"color": "#ffc107", "fontWeight": "500"})
        ])
    return dbc.Alert(message_parts, color="success", className="mb-0", dismissable=True)


def create_no_neighbors_alert():
    """Create an info alert for when no new neighbors are found
    
    Returns:
        dbc.Alert: Info alert component
    """
    return dbc.Alert([
        html.I(className="fas fa-info-circle me-2"),
        "No new neighbors found. Node may have no connections or all neighbors already loaded."
    ], color="info", className="mb-0", dismissable=True, duration=4000)


def create_expansion_error_alert(error_message, error_type="general"):
    """Create an error alert for expansion failures
    
    Args:
        error_message (str): The error message to display
        error_type (str): Type of error ('general', 'timeout', 'connection')
    
    Returns:
        dbc.Alert: Error alert component
    """
    icon_map = {
        'general': 'fa-exclamation-circle',
        'timeout': 'fa-clock',
        'connection': 'fa-plug'
    }
    icon = icon_map.get(error_type, 'fa-exclamation-triangle')
    
    color = 'warning' if error_type == 'timeout' else 'danger'
    
    return dbc.Alert([
        html.I(className=f"fas {icon} me-2"),
        error_message
    ], color=color, className="mb-0", dismissable=True)


def create_node_legend(node_types=None):
    """Create a legend showing node types and their colors
    
    Args:
        node_types (list, optional): List of node types to display in the legend.
                                    If None or empty, shows a message to execute a query.
    
    Returns:
        html.Div: Legend component
    """
    # Get node type styles from the stylesheet (single source of truth)
    all_node_styles = get_node_type_styles()
    
    # If no node types specified, show empty state
    if not node_types:
        return html.Div([
            html.Div([
                html.I(className="fas fa-info-circle fa-lg mb-2", style={"color": "#adb5bd"}),
                html.P(
                    "Execute a query to see the graph",
                    className="text-muted mb-2",
                    style={"fontSize": "13px"}
                ),
                html.P(
                    "Click a node or edge to view details",
                    className="text-muted mb-0",
                    style={"fontSize": "12px"}
                )
            ], className="text-center", style={"marginTop": "100px"})
        ])
    
    # Build legend items for each node type present in the graph
    legend_items = []
    for node_type in sorted(node_types):
        # Get style for this node type, fall back to default if not found
        style_info = all_node_styles.get(node_type, all_node_styles.get('default', {}))
        
        legend_items.append(
            html.Div([
                html.Div(
                    style={
                        "width": "20px",
                        "height": "20px",
                        "borderRadius": "50%",
                        "backgroundColor": style_info.get('color', '#B8B8B8'),
                        "border": f"2px solid {style_info.get('border', '#9E9E9E')}",
                        "display": "inline-block",
                        "marginRight": "10px",
                        "verticalAlign": "middle"
                    }
                ),
                html.Span(
                    node_type,
                    style={
                        "fontSize": "13px",
                        "color": "#495057",
                        "verticalAlign": "middle"
                    }
                )
            ], style={"marginBottom": "12px"})
        )
    
    return html.Div([
        html.Div([
            html.I(className="fas fa-palette fa-lg mb-2", style={"color": "#6c757d"}),
            html.H6(
                "Node Legend",
                className="mt-2 mb-3",
                style={"fontWeight": "600", "color": "#333", "fontSize": "14px"}
            )
        ], className="text-center"),
        html.Div(legend_items, style={"marginTop": "20px"}),
        html.Hr(style={"margin": "20px 0"}),
        html.Div([
            html.I(className="fas fa-info-circle me-2", style={"color": "#6c757d", "fontSize": "12px"}),
            html.Span(
                "Click a node or edge to view details",
                className="text-muted",
                style={"fontSize": "12px"}
            )
        ], className="text-center")
    ], style={"padding": "20px"})
