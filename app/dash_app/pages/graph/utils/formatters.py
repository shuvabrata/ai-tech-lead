"""Property formatting utilities

Functions for formatting node/edge property values for display.
"""

from dash import html
from app.dash_app.styles import (
    PROPERTY_COMPLEX_VALUE_STYLE,
    PROPERTY_SIMPLE_VALUE_STYLE,
    PROPERTY_LABEL_STYLE
)


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
            style=PROPERTY_COMPLEX_VALUE_STYLE
        )
    else:
        return html.Span(
            str(value),
            style=PROPERTY_SIMPLE_VALUE_STYLE
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
                html.Strong(f"{key}: ", style=PROPERTY_LABEL_STYLE),
                format_property_value(value)
            ], className="mb-2")
        )
    return prop_items
