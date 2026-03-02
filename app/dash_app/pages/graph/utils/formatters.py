"""Property formatting utilities

Functions for formatting node/edge property values for display.
"""

from dash import html


def format_property_value(value):
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


def build_property_items(properties):
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
                format_property_value(value)
            ], className="mb-2")
        )
    return prop_items
