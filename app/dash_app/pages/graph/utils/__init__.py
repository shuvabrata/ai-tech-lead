"""Utility functions for graph visualization

This package contains pure utility functions organized by purpose:
- data_transform: Convert data formats, parse errors
- ui_components: Build UI elements (alerts, tables, metrics)
- formatters: Format property values for display
"""

from .data_transform import neo4j_to_cytoscape, parse_error_response
from .ui_components import (
    create_error_alert,
    create_table_display,
    create_graph_success_alert,
    create_performance_metrics,
    toggle_details_panel,
    create_node_legend,
    create_expansion_success_alert,
    create_no_neighbors_alert,
    create_expansion_error_alert
)
from .formatters import format_property_value, build_property_items
from .graph_operations import (
    get_graph_api_base_url,
    get_graph_expand_url,
    execute_expansion_and_merge
)

__all__ = [
    # Data transformation
    'neo4j_to_cytoscape',
    'parse_error_response',
    # UI components
    'create_error_alert',
    'create_table_display',
    'create_graph_success_alert',
    'create_performance_metrics',
    'toggle_details_panel',
    'create_node_legend',
    # Expansion-specific alerts
    'create_expansion_success_alert',
    'create_no_neighbors_alert',
    'create_expansion_error_alert',
    # Formatters
    'format_property_value',
    'build_property_items',
    # Graph operations
    'get_graph_api_base_url',
    'get_graph_expand_url',
    'execute_expansion_and_merge'
]
